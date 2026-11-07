from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.db.models import NotificationModel, VacancyModel


pytestmark = pytest.mark.asyncio(loop_scope="session")


# ------------------------------------------------------------------ чтение

async def test_get_by_external_id(vacancy_repo, create_vacancy):
    vacancy = await create_vacancy(source="dou", external_id="777")

    assert (await vacancy_repo.get_by_external_id("dou", "777")).id == vacancy.id
    assert await vacancy_repo.get_by_external_id("djinni", "777") is None   # тот же id на другом сайте
    assert await vacancy_repo.get_by_external_id("dou", "000") is None


async def test_get_by_keys(vacancy_repo, create_vacancy):
    v1 = await create_vacancy(source="dou", external_id="1")
    v2 = await create_vacancy(source="djinni", external_id="1")
    await create_vacancy(source="dou", external_id="2")

    found = await vacancy_repo.get_by_keys([("dou", "1"), ("djinni", "1"), ("dou", "999")])

    assert {v.id for v in found} == {v1.id, v2.id}
    assert await vacancy_repo.get_by_keys([]) == []


async def test_known_external_ids(vacancy_repo, create_vacancy):
    await create_vacancy(source="dou", external_id="1")
    await create_vacancy(source="dou", external_id="2")
    await create_vacancy(source="djinni", external_id="3")

    known = await vacancy_repo.known_external_ids("dou", ["1", "3", "4"])

    assert known == {"1"}   # "3" есть, но на другом сайте; "4" вообще нет
    assert await vacancy_repo.known_external_ids("dou", []) == set()


async def test_list_recent_orders_by_first_seen_and_filters_by_source(vacancy_repo, create_vacancy, now):
    oldest = await create_vacancy(source="dou", first_seen_at=now - timedelta(days=3))
    newest = await create_vacancy(source="dou", first_seen_at=now - timedelta(days=1))
    middle = await create_vacancy(source="dou", first_seen_at=now - timedelta(days=2))
    djinni = await create_vacancy(source="djinni", first_seen_at=now - timedelta(hours=1))

    everything = await vacancy_repo.list_recent()
    only_dou = await vacancy_repo.list_recent("dou", limit=2)

    assert [v.id for v in everything] == [djinni.id, newest.id, middle.id, oldest.id]
    assert [v.id for v in only_dou] == [newest.id, middle.id]


async def test_count_by_source(vacancy_repo, create_vacancy):
    await create_vacancy(source="dou")
    await create_vacancy(source="dou")
    await create_vacancy(source="dou", is_active=False)
    await create_vacancy(source="djinni")

    assert await vacancy_repo.count_by_source() == {"dou": 2, "djinni": 1}
    assert await vacancy_repo.count_by_source(only_active=False) == {"dou": 3, "djinni": 1}


# ------------------------------------------------------------------ upsert_many

async def test_upsert_many_inserts_new_vacancies(vacancy_repo, make_domain_vacancy, db_value):
    first = make_domain_vacancy(title="Backend", company="ACME", locations=("Київ", "віддалено"), tags=("Python",))
    second = make_domain_vacancy(source="djinni")

    result = await vacancy_repo.upsert_many([first, second])

    assert len(result.new) == 2
    assert result.existing == []
    assert await vacancy_repo.count() == 2

    saved = await vacancy_repo.get_by_external_id("dou", first.id)
    assert (saved.title, saved.company, saved.locations, saved.tags) == (
        "Backend", "ACME", ["Київ", "віддалено"], ["Python"]
    )
    assert saved.description == first.text           # поле text доменной вакансии -> description
    assert saved.is_active is True


async def test_upsert_many_separates_new_from_existing_and_keeps_fields(vacancy_repo, make_domain_vacancy):
    known = make_domain_vacancy(title="Original title")
    await vacancy_repo.upsert_many([known])

    changed = make_domain_vacancy(id=known.id, title="Changed title")
    brand_new = make_domain_vacancy()
    result = await vacancy_repo.upsert_many([changed, brand_new])

    assert [v.external_id for v in result.new] == [brand_new.id]
    assert [v.external_id for v in result.existing] == [known.id]
    assert result.existing[0].title == "Original title"   # поля существующей вакансии не перезаписываются
    assert await vacancy_repo.count() == 2


async def test_upsert_many_refreshes_last_seen_and_reactivates(vacancy_repo, create_vacancy, make_domain_vacancy, now):
    closed = await create_vacancy(
        source="dou",
        external_id="555",
        is_active=False,
        closed_at=now - timedelta(days=1),
        last_seen_at=now - timedelta(days=2),
    )
    old_last_seen = closed.last_seen_at

    result = await vacancy_repo.upsert_many([make_domain_vacancy(source="dou", id="555")])

    assert result.new == []
    revived = result.existing[0]
    assert revived.id == closed.id
    assert revived.is_active is True
    assert revived.closed_at is None
    assert revived.last_seen_at > old_last_seen


async def test_upsert_many_collapses_duplicates_and_handles_empty_input(vacancy_repo, make_domain_vacancy):
    vacancy = make_domain_vacancy()

    result = await vacancy_repo.upsert_many([vacancy, vacancy])
    empty = await vacancy_repo.upsert_many([])

    assert len(result.new) == 1
    assert await vacancy_repo.count() == 1
    assert empty.new == [] and empty.existing == []


# ------------------------------------------------------------------ закрытие и очистка

async def test_mark_inactive(vacancy_repo, create_vacancy, db_value):
    v1 = await create_vacancy()
    v2 = await create_vacancy()

    changed = await vacancy_repo.mark_inactive([v1.id, v2.id])

    assert changed == 2
    assert await db_value(VacancyModel.is_active, VacancyModel.id == v1.id) is False
    assert await db_value(VacancyModel.closed_at, VacancyModel.id == v1.id) is not None
    assert await vacancy_repo.mark_inactive([v1.id]) == 0   # уже закрыта
    assert await vacancy_repo.mark_inactive([]) == 0
    assert await vacancy_repo.mark_inactive([uuid4()]) == 0


async def test_get_stale_returns_only_active_old_vacancies_of_source(vacancy_repo, create_vacancy, now):
    threshold = now - timedelta(days=1)
    oldest = await create_vacancy(source="dou", last_seen_at=now - timedelta(days=3))
    older = await create_vacancy(source="dou", last_seen_at=now - timedelta(days=2))
    await create_vacancy(source="dou", last_seen_at=now - timedelta(days=3), is_active=False)   # уже закрыта
    await create_vacancy(source="djinni", last_seen_at=now - timedelta(days=3))                 # другой сайт
    await create_vacancy(source="dou", last_seen_at=now)                                        # недавно видели

    stale = await vacancy_repo.get_stale("dou", threshold)
    limited = await vacancy_repo.get_stale("dou", threshold, limit=1)

    assert [v.id for v in stale] == [oldest.id, older.id]   # самые давние первыми
    assert [v.id for v in limited] == [oldest.id]


async def test_delete_closed_before_removes_only_old_closed_vacancies(
    vacancy_repo, create_vacancy, create_notification, user, db_session, now
):
    old_closed = await create_vacancy(is_active=False, closed_at=now - timedelta(days=10))
    recently_closed = await create_vacancy(is_active=False, closed_at=now - timedelta(hours=1))
    active = await create_vacancy()
    await create_notification(user, old_closed)

    deleted = await vacancy_repo.delete_closed_before(now - timedelta(days=1))

    assert deleted == 1
    assert await vacancy_repo.exists(old_closed.id) is False
    assert await vacancy_repo.exists(recently_closed.id) is True
    assert await vacancy_repo.exists(active.id) is True
    # уведомления удалённой вакансии удаляются каскадом на уровне БД
    notifications = await db_session.scalar(select(func.count()).select_from(NotificationModel))
    assert notifications == 0