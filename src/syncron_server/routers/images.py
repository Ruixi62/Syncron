"""Images : hébergement d'images pour les membres, avec un lien public à partager (Discord…).

Tout compte connecté envoie des images (quota par membre, espace total plafonné), voit la
galerie du pays, renomme et supprime les siennes. Les comptes qui gèrent le système
« images » suppriment n'importe laquelle. Le fichier est servi par `/media/images/<jeton>`,
une adresse aléatoire : seuls ceux à qui on donne le lien peuvent voir l'image.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from syncron_server import audit
from syncron_server.deps import SessionDep, SettingsDep, UserDep
from syncron_server.media import MEDIA_PREFIX, ImageError, delete_image, normalize_hosted, store_hosted
from syncron_server.models import HostedImage, User, utcnow
from syncron_server.schemas import (
    HostedImageOut,
    HostedImagePatch,
    HostedImagesOut,
    OverviewStat,
    SystemOverviewOut,
)
from syncron_server.systems import IMAGES, SYSTEMS, overview_provider

router = APIRouter(prefix="/api/v1/images", tags=["Images"])
PAGE_SIZE = 500


def _can_delete(image: HostedImage, user: User) -> bool:
    return image.uploaded_by == user.id or user.can_manage(IMAGES)


def _out(image: HostedImage, user: User) -> HostedImageOut:
    uploader = image.uploader
    return HostedImageOut(
        id=image.id,
        url=MEDIA_PREFIX + image.path,
        title=image.title,
        content_type=image.content_type,
        width=image.width,
        height=image.height,
        size_bytes=image.size_bytes,
        uploader=(uploader.display_name or uploader.username) if uploader else None,
        mine=image.uploaded_by == user.id,
        can_delete=_can_delete(image, user),
        created_at=image.created_at,
    )


async def _count(session: AsyncSession, user: User) -> int:
    query = select(func.count()).select_from(HostedImage).where(HostedImage.uploaded_by == user.id)
    return (await session.execute(query)).scalar_one()


def _title(filename: str | None, title: str | None) -> str:
    chosen = (title or "").strip() or Path(filename or "").stem.replace("_", " ").strip()
    return " ".join(chosen.split())[:120] or "Image"


@router.get("", response_model=HostedImagesOut)
async def list_images(
    session: SessionDep,
    settings: SettingsDep,
    user: UserDep,
    mine: Annotated[bool, Query()] = False,
) -> HostedImagesOut:
    query = select(HostedImage).order_by(HostedImage.created_at.desc(), HostedImage.id).limit(PAGE_SIZE)
    if mine:
        query = query.where(HostedImage.uploaded_by == user.id)
    images = list((await session.execute(query)).scalars())
    mine_count = await _count(session, user)
    await session.commit()
    return HostedImagesOut(
        images=[_out(image, user) for image in images],
        mine_count=mine_count,
        per_user_limit=settings.hosted_images_per_user,
        max_bytes=settings.max_hosted_image_bytes,
    )


@router.post("", response_model=HostedImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    session: SessionDep,
    settings: SettingsDep,
    user: UserDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=120)] = None,
) -> HostedImageOut:
    limit = settings.hosted_images_per_user
    if limit and await _count(session, user) >= limit:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Tu as atteint la limite de {limit} images : supprimes-en avant d'en ajouter."
        )
    raw = await file.read(settings.max_hosted_image_bytes + 1)
    try:
        hosted = normalize_hosted(raw, settings.max_hosted_image_bytes)
    except ImageError as exc:
        raise HTTPException(422, str(exc)) from exc
    total_limit = settings.hosted_images_total_bytes
    if total_limit:
        used = (await session.execute(select(func.coalesce(func.sum(HostedImage.size_bytes), 0)))).scalar_one()
        if used + len(hosted.content) > total_limit:
            raise HTTPException(
                status.HTTP_507_INSUFFICIENT_STORAGE, "L'espace réservé aux images est plein : préviens l'équipe."
            )
    relative = store_hosted(settings.media_dir, hosted)
    image = HostedImage(
        id=uuid.uuid4(),
        path=relative,
        title=_title(file.filename, title),
        content_type=hosted.content_type,
        width=hosted.width,
        height=hosted.height,
        size_bytes=len(hosted.content),
        uploaded_by=user.id,
        created_at=utcnow(),
    )
    session.add(image)
    audit.record(session, user.id, IMAGES, "image.upload", "image", str(image.id), f"Image envoyée : {image.title}")
    try:
        await session.commit()
    except Exception:
        delete_image(settings.media_dir, MEDIA_PREFIX + relative)
        raise
    image.uploader = user
    return _out(image, user)


async def _owned(session: AsyncSession, image_id: uuid.UUID, user: User) -> HostedImage:
    image = await session.get(HostedImage, image_id, with_for_update=True)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image introuvable.")
    if not _can_delete(image, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul l'auteur de l'image, ou l'équipe, peut la modifier.")
    return image


@router.patch("/{image_id}", response_model=HostedImageOut)
async def rename_image(
    image_id: uuid.UUID, payload: HostedImagePatch, session: SessionDep, user: UserDep
) -> HostedImageOut:
    image = await _owned(session, image_id, user)
    image.title = _title(None, payload.title)
    audit.record(session, user.id, IMAGES, "image.rename", "image", str(image.id), f"Image renommée : {image.title}")
    await session.commit()
    await session.refresh(image, ["uploader"])
    return _out(image, user)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hosted(image_id: uuid.UUID, session: SessionDep, settings: SettingsDep, user: UserDep) -> None:
    image = await _owned(session, image_id, user)
    url = MEDIA_PREFIX + image.path
    title = image.title
    await session.delete(image)
    audit.record(session, user.id, IMAGES, "image.delete", "image", str(image_id), f"Image supprimée : {title}")
    await session.commit()
    delete_image(settings.media_dir, url)


@overview_provider(IMAGES)
async def overview(session: AsyncSession) -> SystemOverviewOut:
    count, used, last = (
        await session.execute(
            select(
                func.count(HostedImage.id),
                func.coalesce(func.sum(HostedImage.size_bytes), 0),
                func.max(HostedImage.created_at),
            )
        )
    ).one()
    members = (await session.execute(select(func.count(func.distinct(HostedImage.uploaded_by))))).scalar_one()
    megabytes = used / (1024 * 1024)
    return SystemOverviewOut(
        id=IMAGES,
        name=SYSTEMS[IMAGES],
        stats=[
            OverviewStat(label="Images hébergées", value=str(count), detail=f"envoyées par {members} membre(s)"),
            OverviewStat(label="Espace utilisé", value=f"{megabytes:.1f} Mo".replace(".", ",")),
        ],
        updated_at=last,
    )
