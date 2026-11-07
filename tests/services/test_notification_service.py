import pytest

from src.db.models import NotificationStatus
from src.services import DeliveryReport

pytestmark = pytest.mark.asyncio(loop_scope="session")

SENT = NotificationStatus.SENT
SKIPPED = NotificationStatus.SKIPPED
FAILED = NotificationStatus.FAILED


async def test_deliver_pending_without_pending_does_nothing(delivery_service, notifier):
    assert await delivery_service.deliver_pending() == DeliveryReport()
    assert notifier.sent == []


async def test_deliver_pending_sends_vacancies_and_marks_them_sent(
    delivery_service, subscribe, publish, notifier, db_notifications
):
    await subscribe(1)
    await subscribe(2)
    vacancy = await publish()

    report = await delivery_service.deliver_pending()

    assert report.sent == 2
    assert report.failed == 0
    assert notifier.recipients(vacancy.id) == [1, 2]
    assert {status for _, _, status in await db_notifications()} == {SENT}
    assert (await delivery_service.deliver_pending()).sent == 0   # повторно ничего не уходит


async def test_blocked_user_is_deactivated_and_others_still_receive(
    delivery_service, user_service, subscribe, publish, notifier, db_notifications
):
    await subscribe(1)
    await subscribe(2)
    vacancy = await publish()
    notifier.blocked.add(1)

    report = await delivery_service.deliver_pending()

    assert report.users_deactivated == 1
    assert report.sent == 1
    assert (await user_service.get(1)).is_active is False
    assert notifier.recipients(vacancy.id) == [2]
    assert {telegram_id: status for telegram_id, _, status in await db_notifications()} == {1: SKIPPED, 2: SENT}


async def test_rate_limit_is_waited_out_and_vacancy_is_still_sent(delivery_service, subscribe, publish, notifier):
    await subscribe(1)
    vacancy = await publish()
    notifier.rate_limited[1] = 1   # первый раз Telegram просит подождать

    report = await delivery_service.deliver_pending()

    assert report.sent == 1
    assert notifier.recipients(vacancy.id) == [1]


async def test_failed_delivery_is_retried_until_max_attempts(
    delivery_service, subscribe, publish, notifier, db_notifications
):
    await subscribe(1)
    await publish()
    notifier.failing.add(1)

    for _ in range(3):   # max_delivery_attempts == 3: одна попытка за вызов
        assert (await delivery_service.deliver_pending()).failed == 1

    assert {status for _, _, status in await db_notifications()} == {FAILED}
    assert (await delivery_service.deliver_pending()).failed == 0   # после FAILED больше не пробуем


async def test_pending_of_inactive_user_is_skipped_not_sent(
    delivery_service, user_service, subscribe, publish, notifier, deactivate_in_db, db_notifications
):
    await subscribe(1)
    await publish()
    user = await user_service.get(1)
    await deactivate_in_db(user.id)   # в обход UserService.deactivate

    report = await delivery_service.deliver_pending()

    assert report.skipped == 1
    assert report.sent == 0
    assert notifier.sent == []
    assert {status for _, _, status in await db_notifications()} == {SKIPPED}
