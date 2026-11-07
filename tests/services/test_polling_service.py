import pytest

from src.db.models import NotificationStatus

pytestmark = pytest.mark.asyncio(loop_scope="session")

PENDING = NotificationStatus.PENDING
SKIPPED = NotificationStatus.SKIPPED


async def test_cycle_without_subscriptions_does_nothing(polling_service, dou_source, djinni_source):
    report = await polling_service.run_cycle()

    assert report.subscriptions == 0
    assert report.queries_planned == 0
    assert dou_source.fetch_calls == [] and djinni_source.fetch_calls == []


# ------------------------------------------------------------------ запросы к сайтам

async def test_same_filters_of_several_users_make_one_request_per_site(
    polling_service, subscribe, dou_source, djinni_source
):
    for telegram_id in (1, 2, 3):
        await subscribe(telegram_id, sources=["dou", "djinni"])
    dou_source.fetch_calls.clear()
    djinni_source.fetch_calls.clear()

    report = await polling_service.run_cycle()

    assert len(dou_source.fetch_calls) == 1
    assert len(djinni_source.fetch_calls) == 1
    assert report.subscriptions == 3
    assert report.queries_planned == 2


async def test_different_filters_make_different_requests(polling_service, subscribe, dou_source):
    await subscribe(1, categories=["Python"])
    await subscribe(2, categories=["Java"])
    dou_source.fetch_calls.clear()

    await polling_service.run_cycle()

    assert sorted(q.category for q in dou_source.fetch_calls) == ["Java", "Python"]


# ------------------------------------------------------------------ новые вакансии и уведомления

async def test_new_vacancy_creates_pending_notifications_for_matching_users(
    polling_service, subscribe, dou_source, make_vacancy, db_notifications
):
    await subscribe(1)
    await subscribe(2)
    await subscribe(3, categories=["Java"])
    vacancy = make_vacancy("dou")
    dou_source.add("Python", vacancy)

    report = await polling_service.run_cycle()

    assert report.vacancies_fetched == 1
    assert report.new_vacancies == 1
    assert report.notifications_created == 2
    assert set(await db_notifications(PENDING)) == {(1, vacancy.id, PENDING), (2, vacancy.id, PENDING)}


async def test_known_vacancy_is_not_notified_twice(polling_service, subscribe, dou_source, make_vacancy, db_notifications):
    await subscribe(1)
    dou_source.add("Python", make_vacancy("dou"))

    first = await polling_service.run_cycle()
    second = await polling_service.run_cycle()

    assert first.notifications_created == 1
    assert second.new_vacancies == 0
    assert second.notifications_created == 0
    assert len(await db_notifications(PENDING)) == 1


async def test_vacancy_matching_two_subscriptions_of_one_user_is_notified_once(
    polling_service, subscribe, dou_source, make_vacancy, db_notifications
):
    await subscribe(1)
    await subscribe(1, employments=["remote"])
    dou_source.add("Python", make_vacancy("dou"))

    report = await polling_service.run_cycle()

    assert report.notifications_created == 1
    assert len(await db_notifications(PENDING)) == 1


async def test_keyword_filters_are_applied_locally(polling_service, subscribe, dou_source, make_vacancy, db_notifications):
    await subscribe(1, keywords=["django"])
    await subscribe(2)
    flask = make_vacancy("dou", title="Python Flask developer")
    django = make_vacancy("dou", title="Python Django developer")
    dou_source.add("Python", flask, django)

    await polling_service.run_cycle()

    assert set(await db_notifications(PENDING)) == {
        (1, django.id, PENDING),
        (2, flask.id, PENDING),
        (2, django.id, PENDING),
    }


async def test_paused_subscriptions_and_deactivated_users_are_ignored(
    polling_service, subscribe, subscription_service, user_service, dou_source, make_vacancy, db_notifications
):
    paused = await subscribe(1)
    await subscribe(2)
    await subscription_service.set_active(1, paused.id, False)
    await user_service.deactivate(2)
    dou_source.add("Python", make_vacancy("dou"))

    report = await polling_service.run_cycle()

    assert report.subscriptions == 0
    assert await db_notifications() == []


# ------------------------------------------------------------------ засев

async def test_seeding_marks_current_vacancies_as_skipped_not_pending(
    subscribe, dou_source, make_vacancy, db_notifications
):
    existing = [make_vacancy("dou"), make_vacancy("dou")]
    dou_source.add("Python", *existing)

    subscription = await subscribe(1)

    assert subscription.is_seeded is True
    assert await db_notifications(PENDING) == []
    assert {(telegram_id, vacancy_id) for telegram_id, vacancy_id, _ in await db_notifications(SKIPPED)} == {
        (1, vacancy.id) for vacancy in existing
    }


async def test_failed_request_does_not_break_cycle_and_postpones_seeding(
    polling_service, subscribe, subscription_service, dou_source, make_vacancy, db_notifications
):
    dou_source.add("Python", make_vacancy("dou"))   # эта вакансия уже есть на сайте
    dou_source.fail = True

    subscription = await subscribe(1)

    assert subscription.is_seeded is False   # сайт не ответил: засев не удался
    failed_cycle = await polling_service.run_cycle()
    assert failed_cycle.queries_failed == 1
    assert failed_cycle.subscriptions_seeded == 0

    dou_source.fail = False
    recovered_cycle = await polling_service.run_cycle()

    assert recovered_cycle.subscriptions_seeded == 1
    assert await db_notifications(PENDING) == []   # старая вакансия не превратилась в «новую»
    assert (await subscription_service.get(1, subscription.id)).is_seeded is True
