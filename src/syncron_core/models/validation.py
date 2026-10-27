"""Rapport de validation des données (erreurs de saisie dans les JSON)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    message: str
    item_id: str | None = None
    source: str = ""
    section: str = "items"

    def __str__(self) -> str:
        where = f"[{self.section}:{self.item_id}] " if self.item_id else ""
        origin = f" ({self.source})" if self.source else ""
        return f"{where}{self.message}{origin}"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is Severity.WARNING)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is Severity.ERROR for issue in self.issues)

    @property
    def item_ids_with_errors(self) -> frozenset[str]:
        return frozenset(i.item_id for i in self.errors if i.item_id and i.section == "items")

    def merged(self, other: ValidationReport) -> ValidationReport:
        return ValidationReport(self.issues + other.issues)

    def __bool__(self) -> bool:
        return bool(self.issues)

    def __len__(self) -> int:
        return len(self.issues)
