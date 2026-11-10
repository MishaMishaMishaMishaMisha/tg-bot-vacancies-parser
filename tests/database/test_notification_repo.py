from datetime import timedelta
from uuid import uuid4

import pytest

from src.db.models import NotificationModel, NotificationStatus
from src.db.repositories import NewNotification


pytestmark = pytest.mark.asyncio(loop_scope="session")



async def test_add_many_if_absent_creates_pending_notifications(
    notification_repo, user, other_user, create_vacancy
):
    v1, v2 = await create_vacancy(), await create_vacancy()
    items = [NewNotification(user.id, v1.id), NewNotification(other_user.id, v2.id)]

    created = await notification_repo.add_many_if_absent(items)

    assert len(created) == 2
    assert {n.status for n in created} == {NotificationStatus.PENDING}
    assert {(n.user_id, n.vacancy_id) for n in created} == {(user.id, v1.id), (other_user.id, v2.id)}


async def test_add_many_if_absent_returns_only_newly_created(notification_repo, user, create_vacancy):
    v1, v2 = await create_vacancy(), await create_vacancy()
    await notification_repo.add_many_if_absent([NewNotification(user.id, v1.id)])

    created = await notification_repo.add_many_if_absent(
        [NewNotification(user.id, v1.id), NewNotification(user.id, v2.id)]
    )

    assert [(n.user_id, n.vacancy_id) for n in created] == [(user.id, v2.id)]
    assert await notification_repo.count() == 2


async def test_add_many_if_absent_with_custom_status_subscription_and_duplicates(
    notification_repo, user, create_vacancy, create_subscription
):
    subscription = await create_subscription(user)
    vacancy = await create_vacancy()
    item = NewNotification(user.id, vacancy.id, subscription.id)

    created = await notification_repo.add_many_if_absent([item, item], status=NotificationStatus.SKIPPED)

    assert len(created) == 1   # дубликаты в одной пачке схлопнулись
    assert created[0].status == NotificationStatus.SKIPPED
    assert created[0].subscription_id == subscription.id
    assert await notification_repo.add_many_if_absent([]) == []


async def test_get_notified_vacancy_ids_is_per_user(
    notification_repo, user, other_user, create_vacancy, create_notification
):
    v1, v2, v3 = await create_vacancy(), await create_vacancy(), await create_vacancy()
    await create_notification(user, v1)
    await create_notification(other_user, v2)

    notified = await notification_repo.get_notified_vacancy_ids(user.id, [v1.id, v2.id, v3.id])

    assert notified == {v1.id}
    assert await notification_repo.get_notified_vacancy_ids(user.id, []) == set()



async def test_list_pending_returns_pending_with_user_and_vacancy_loaded(
    notification_repo, user, create_vacancy, create_notification
):
    pending_1 = await create_notification(user, await create_vacancy(title="First"))
    pending_2 = await create_notification(user, await create_vacancy(title="Second"))
    await create_notification(user, await create_vacancy(), status=NotificationStatus.SENT)

    pending = await notification_repo.list_pending()

    assert {n.id for n in pending} == {pending_1.id, pending_2.id}
    assert {n.vacancy.title for n in pending} == {"First", "Second"}   # связи подгружены без ленивой загрузки
    assert all(n.user.telegram_id == user.telegram_id for n in pending)


async def test_list_pending_supports_limit_and_lock(notification_repo, user, create_vacancy, create_notification):
    for _ in range(3):
        await create_notification(user, await create_vacancy())

    assert len(await notification_repo.list_pending(limit=2)) == 2
    assert len(await notification_repo.list_pending(lock=True)) == 3   # FOR UPDATE SKIP LOCKED


async def test_mark_sent(notification_repo, user, create_vacancy, create_notification, db_value):
    n1 = await create_notification(user, await create_vacancy(), last_error="timeout")
    n2 = await create_notification(user, await create_vacancy())

    changed = await notification_repo.mark_sent([n1.id, n2.id])

    assert changed == 2
    assert await db_value(NotificationModel.status, NotificationModel.id == n1.id) == NotificationStatus.SENT
    assert await db_value(NotificationModel.sent_at, NotificationModel.id == n1.id) is not None
    assert await db_value(NotificationModel.last_error, NotificationModel.id == n1.id) is None
    assert await notification_repo.mark_sent([]) == 0


async def test_register_failure_retries_until_max_attempts(
    notification_repo, user, create_vacancy, create_notification
):
    notification = await create_notification(user, await create_vacancy())

    after_first = await notification_repo.register_failure(notification.id, "boom", max_attempts=2)
    assert (after_first.attempts, after_first.status, after_first.last_error) == (
        1, NotificationStatus.PENDING, "boom"
    )

    after_second = await notification_repo.register_failure(notification.id, "boom again", max_attempts=2)
    assert (after_second.attempts, after_second.status) == (2, NotificationStatus.FAILED)

    assert await notification_repo.register_failure(uuid4(), "boom") is None


async def test_register_failure_truncates_long_error(notification_repo, user, create_vacancy, create_notification):
    notification = await create_notification(user, await create_vacancy())

    result = await notification_repo.register_failure(notification.id, "x" * 2000)

    assert len(result.last_error) == 1000


async def test_skip_pending_for_user_touches_only_that_users_pending(
    notification_repo, user, other_user, create_vacancy, create_notification, db_value
):
    pending_1 = await create_notification(user, await create_vacancy())
    pending_2 = await create_notification(user, await create_vacancy())
    already_sent = await create_notification(user, await create_vacancy(), status=NotificationStatus.SENT)
    others = await create_notification(other_user, await create_vacancy())

    skipped = await notification_repo.skip_pending_for_user(user.id)

    assert skipped == 2

    async def status_of(notification):
        return await db_value(NotificationModel.status, NotificationModel.id == notification.id)

    assert await status_of(pending_1) == NotificationStatus.SKIPPED
    assert await status_of(pending_2) == NotificationStatus.SKIPPED
    assert await status_of(already_sent) == NotificationStatus.SENT
    assert await status_of(others) == NotificationStatus.PENDING



async def test_count_by_status(notification_repo, user, create_vacancy, create_notification):
    await create_notification(user, await create_vacancy())
    await create_notification(user, await create_vacancy())
    await create_notification(user, await create_vacancy(), status=NotificationStatus.SENT)

    counts = await notification_repo.count_by_status()

    assert counts == {NotificationStatus.PENDING: 2, NotificationStatus.SENT: 1}


async def test_delete_older_than_keeps_pending_and_recent(
    notification_repo, user, create_vacancy, create_notification, now
):
    old_sent = await create_notification(
        user, await create_vacancy(), status=NotificationStatus.SENT, created_at=now - timedelta(days=60)
    )
    old_pending = await create_notification(
        user, await create_vacancy(), status=NotificationStatus.PENDING, created_at=now - timedelta(days=60)
    )
    recent_sent = await create_notification(user, await create_vacancy(), status=NotificationStatus.SENT)

    deleted = await notification_repo.delete_older_than(now - timedelta(days=30))

    assert deleted == 1
    assert await notification_repo.exists(old_sent.id) is False
    assert await notification_repo.exists(old_pending.id) is True    # неотправленное не удаляем
    assert await notification_repo.exists(recent_sent.id) is True