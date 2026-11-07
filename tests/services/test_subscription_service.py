from uuid import uuid4

import pytest
import pytest_asyncio

from src.services import (
    SubscriptionFilters,
    SubscriptionLimitError,
    SubscriptionNotFoundError,
    UserNotFoundError,
    ValidationError,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

USER = 1000

INVALID_FILTERS = {
    "no sources": SubscriptionFilters(),
    "unknown source": SubscriptionFilters(sources=["nope"]),
    "category is on no site": SubscriptionFilters(sources=["dou"], categories=["Rust"]),
    "unknown experience": SubscriptionFilters(sources=["dou"], experiences=["abc"]),
    "salary out of range": SubscriptionFilters(sources=["djinni"], min_salary=99_999),
    "unknown english level": SubscriptionFilters(sources=["djinni"], english_levels=["klingon"]),
    "only filters the site cannot do": SubscriptionFilters(sources=["dou"], english_levels=["basic"]),
    "too many combinations": SubscriptionFilters(
        sources=["dou"],
        categories=["Python", "Java"],
        experiences=["none", "0-1", "1-3", "3-5", "5plus"],
        employments=["remote", "parttime", "office"],
    ),
}


@pytest_asyncio.fixture
async def registered(user_service):
    return await user_service.register(USER, username="tester")


# ------------------------------------------------------------------ create

async def test_create_normalizes_filters_and_seeds_subscription(subscription_service, registered):
    filters = SubscriptionFilters(
        sources=["DOU", "dou"],
        categories=["python", "PYTHON"],
        keywords=["Django", "django"],
        exclude_keywords=[" Senior "],
    )

    result = await subscription_service.create(USER, filters, name="  My filter  ")

    saved = result.subscription
    assert saved.filters.sources == ["dou"]
    assert saved.filters.categories == ["python"]
    assert saved.filters.keywords == ["django"]
    assert saved.filters.exclude_keywords == ["senior"]
    assert saved.name == "My filter"
    assert saved.is_active is True
    assert saved.is_seeded is True
    assert result.warnings == []


async def test_create_returns_warnings_when_one_site_cannot_run_the_filters(subscription_service, registered):
    filters = SubscriptionFilters(sources=["dou", "djinni"], english_levels=["basic"])

    result = await subscription_service.create(USER, filters)

    codes = {(w.source, w.code) for w in result.warnings}
    assert ("dou", "unsupported_filter") in codes
    assert ("dou", "source_skipped") in codes
    assert not any(w.source == "djinni" for w in result.warnings)


@pytest.mark.parametrize("filters", list(INVALID_FILTERS.values()), ids=list(INVALID_FILTERS))
async def test_create_rejects_invalid_filters(subscription_service, registered, filters):
    with pytest.raises(ValidationError):
        await subscription_service.create(USER, filters)


async def test_create_requires_registered_user(subscription_service):
    with pytest.raises(UserNotFoundError):
        await subscription_service.create(USER, SubscriptionFilters(sources=["dou"]))


async def test_create_enforces_subscription_limit(subscription_service, registered):
    filters = SubscriptionFilters(sources=["dou"], categories=["Python"])
    for _ in range(3):   # settings.max_subscriptions_per_user == 3
        await subscription_service.create(USER, filters)

    with pytest.raises(SubscriptionLimitError):
        await subscription_service.create(USER, filters)


# ------------------------------------------------------------------ update

async def test_update_replaces_filters_and_reseeds(subscription_service, registered, dou_source):
    created = (await subscription_service.create(
        USER, SubscriptionFilters(sources=["dou"], categories=["Python"]), name="Original"
    )).subscription
    dou_source.fetch_calls.clear()

    updated = (await subscription_service.update(
        USER, created.id, SubscriptionFilters(sources=["dou"], categories=["Java"])
    )).subscription

    assert updated.id == created.id
    assert updated.filters.categories == ["Java"]
    assert updated.name == "Original"                                # имя не передали: осталось прежним
    assert updated.is_seeded is True
    assert [q.category for q in dou_source.fetch_calls] == ["Java"]   # засев пошёл по новым фильтрам

    renamed = (await subscription_service.update(
        USER, created.id, SubscriptionFilters(sources=["dou"], categories=["Java"]), name="Renamed"
    )).subscription
    assert renamed.name == "Renamed"


async def test_update_unknown_or_foreign_subscription_raises(subscription_service, user_service, registered):
    filters = SubscriptionFilters(sources=["dou"], categories=["Python"])
    own = (await subscription_service.create(USER, filters)).subscription
    await user_service.register(2000)

    with pytest.raises(SubscriptionNotFoundError):
        await subscription_service.update(USER, uuid4(), filters)
    with pytest.raises(SubscriptionNotFoundError):
        await subscription_service.update(2000, own.id, filters)   # чужая подписка


# ------------------------------------------------------------------ пауза, удаление, чтение

async def test_set_active_pauses_and_resumes_with_reseeding(subscription_service, registered, dou_source):
    created = (await subscription_service.create(
        USER, SubscriptionFilters(sources=["dou"], categories=["Python"])
    )).subscription

    paused = await subscription_service.set_active(USER, created.id, False)

    assert paused.is_active is False
    assert await subscription_service.list_for_user(USER, only_active=True) == []

    dou_source.fetch_calls.clear()
    resumed = await subscription_service.set_active(USER, created.id, True)

    assert resumed.is_active is True
    assert resumed.is_seeded is True
    assert len(dou_source.fetch_calls) == 1   # после паузы подписка засеяна заново


async def test_delete_only_by_owner(subscription_service, user_service, registered):
    created = (await subscription_service.create(
        USER, SubscriptionFilters(sources=["dou"], categories=["Python"])
    )).subscription
    await user_service.register(2000)

    assert await subscription_service.delete(2000, created.id) is False   # чужая
    assert await subscription_service.delete(USER, created.id) is True
    assert await subscription_service.delete(USER, created.id) is False
    assert await subscription_service.delete(999_999, created.id) is False   # пользователя нет


async def test_get_and_list_for_user(subscription_service, user_service, registered):
    first = (await subscription_service.create(
        USER, SubscriptionFilters(sources=["dou"], categories=["Python"])
    )).subscription
    second = (await subscription_service.create(
        USER, SubscriptionFilters(sources=["dou"], categories=["Java"])
    )).subscription
    await user_service.register(2000)

    listed = await subscription_service.list_for_user(USER)

    assert {s.id for s in listed} == {first.id, second.id}
    assert (await subscription_service.get(USER, first.id)).id == first.id
    with pytest.raises(SubscriptionNotFoundError):
        await subscription_service.get(2000, first.id)
    with pytest.raises(UserNotFoundError):
        await subscription_service.list_for_user(999_999)


async def test_check_validates_without_saving(subscription_service, registered):
    warnings = await subscription_service.check(SubscriptionFilters(sources=["dou"], categories=["Python"]))

    assert warnings == []
    assert await subscription_service.list_for_user(USER) == []
    with pytest.raises(ValidationError):
        await subscription_service.check(SubscriptionFilters())
