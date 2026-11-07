import pytest

from src.services import SubscriptionFilters, ValidationError
from src.services.jobs import Experience, Region, SearchQuery

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_builds_one_query_per_combination_of_filters(builder, dou_source):
    filters = SubscriptionFilters(categories=["Python", "Java"], experiences=["1-3", "3-5"])

    plan = await builder.build(dou_source, filters)

    assert {(q.category, q.experience) for q in plan.queries} == {
        ("Python", Experience.Y1_3),
        ("Python", Experience.Y3_5),
        ("Java", Experience.Y1_3),
        ("Java", Experience.Y3_5),
    }
    assert plan.warnings == []


async def test_no_filters_give_a_single_unrestricted_query(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters())

    assert plan.queries == [SearchQuery()]


async def test_category_names_match_case_insensitively_and_use_the_sites_spelling(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters(categories=["python"]))

    assert [q.category for q in plan.queries] == ["Python"]


async def test_missing_category_gives_no_queries_instead_of_widening_the_filter(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters(categories=["Rust"]))

    assert plan.queries == []
    assert [(w.code, w.detail) for w in plan.warnings] == [("categories_unavailable", "Rust")]


async def test_partially_missing_categories_keep_the_known_ones(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters(categories=["Python", "Rust"]))

    assert [q.category for q in plan.queries] == ["Python"]
    assert [w.code for w in plan.warnings] == ["categories_unavailable"]


async def test_missing_city_gives_no_queries(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters(cities=["Одеса"]))

    assert plan.queries == []
    assert [w.code for w in plan.warnings] == ["cities_unavailable"]


async def test_filters_the_site_cannot_do_are_dropped_with_a_single_warning(builder, dou_source):
    filters = SubscriptionFilters(categories=["Python", "Java"], english_levels=["basic"])

    plan = await builder.build(dou_source, filters)

    assert plan.queries == []
    assert [w.code for w in plan.warnings] == ["unsupported_filter"]   # одна причина, а не по одной на комбинацию


async def test_the_same_filters_work_on_a_site_that_supports_them(builder, djinni_source):
    filters = SubscriptionFilters(english_levels=["basic"], min_salary=3000, regions=["UKR"])

    plan = await builder.build(djinni_source, filters)

    assert plan.queries == [SearchQuery(english="basic", min_salary=3000, region=Region.UKRAINE)]


async def test_invalid_enum_values_are_reported(builder, dou_source):
    plan = await builder.build(dou_source, SubscriptionFilters(experiences=["abc"]))

    assert plan.queries == []
    assert [w.code for w in plan.warnings] == ["experiences_invalid"]


async def test_too_many_combinations_raise_validation_error(builder, dou_source):
    filters = SubscriptionFilters(
        categories=["Python", "Java"],
        experiences=["none", "0-1", "1-3", "3-5", "5plus"],
        employments=["remote", "parttime", "office"],
    )   # 2 * 5 * 3 = 30 при лимите 10

    with pytest.raises(ValidationError):
        await builder.build(dou_source, filters)
