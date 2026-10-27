from __future__ import annotations

from dataclasses import dataclass

import pytest

from syncron_core.calculator import CraftCalculator
from syncron_core.catalog import CraftRepository
from syncron_core.catalog_service import CatalogService

from ..sample import sample_data


@dataclass
class CoreContext:
    repository: CraftRepository
    catalog: CatalogService
    calculator: CraftCalculator


@pytest.fixture
def context() -> CoreContext:
    repository = CraftRepository(sample_data())
    return CoreContext(repository, CatalogService(repository), CraftCalculator(repository))
