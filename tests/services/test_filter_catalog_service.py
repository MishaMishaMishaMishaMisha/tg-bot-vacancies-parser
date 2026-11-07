import pytest

from src.services import FilterCatalogService
from src.services.jobs import Employment, Experience, Region

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_catalog_merges_all_sources(catalog_service, settings):
    catalog = await catalog_service.get_catalog()

    assert catalog.categories == ["Design", "Java", "Python"]   # dou: Python, Java; djinni: Python, Design
    assert catalog.cities == ["Київ", "Львів"]
    assert [level.value for level in catalog.english_levels] == ["basic", "intermediate"]
    assert catalog.experiences == list(Experience)
    assert catalog.employments == list(Employment)
    assert catalog.regions == list(Region)
    assert catalog.max_salary == settings.max_salary


async def test_get_catalog_for_selected_sources_only(catalog_service):
    catalog = await catalog_service.get_catalog(["dou"])

    assert catalog.categories == ["Java", "Python"]
    assert catalog.english_levels == []   # у DOU такого фильтра нет


async def test_get_catalog_ignores_case_when_merging(make_source, settings):
    service = FilterCatalogService(
        {"a": make_source("a", categories=["python"]), "b": make_source("b", categories=["Python", "QA"])},
        settings,
    )

    assert (await service.get_catalog()).categories == ["python", "QA"]


async def test_get_options_and_source_names(catalog_service):
    assert catalog_service.source_names == ["djinni", "dou"]
    assert (await catalog_service.get_options("dou")).categories == ["Python", "Java"]


async def test_refresh_all_reports_result_per_source(catalog_service, djinni_source):
    djinni_source.fail_refresh = True

    assert await catalog_service.refresh_all() == {"djinni": False, "dou": True}
