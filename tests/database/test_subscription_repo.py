from uuid import uuid4

import pytest

from src.db.models import SubscriptionModel

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_for_user_checks_owner(subscription_repo, user, other_user, create_subscription):
    subscription = await create_subscription(user)

    assert (await subscription_repo.get_for_user(subscription.id, user.id)).id == subscription.id
    assert await subscription_repo.get_for_user(subscription.id, other_user.id) is None
    assert await subscription_repo.get_for_user(uuid4(), user.id) is None


async def test_list_by_user(subscription_repo, user, other_user, create_subscription):
    active = await create_subscription(user)
    disabled = await create_subscription(user, is_active=False)
    await create_subscription(other_user)

    all_of_user = await subscription_repo.list_by_user(user.id)
    only_active = await subscription_repo.list_by_user(user.id, only_active=True)

    assert {s.id for s in all_of_user} == {active.id, disabled.id}
    assert {s.id for s in only_active} == {active.id}


async def test_count_by_user(subscription_repo, user, other_user, create_subscription):
    await create_subscription(user)
    await create_subscription(user)
    await create_subscription(other_user)

    assert await subscription_repo.count_by_user(user.id) == 2
    assert await subscription_repo.count_by_user(uuid4()) == 0


async def test_list_active_skips_disabled_subscriptions_and_inactive_users(
    subscription_repo, user, create_user, create_subscription
):
    blocked_user = await create_user(is_active=False)
    dou = await create_subscription(user, sources=["dou"])
    djinni = await create_subscription(user, sources=["djinni"])
    both = await create_subscription(user, sources=["dou", "djinni"])
    await create_subscription(user, is_active=False)      # подписка выключена
    await create_subscription(blocked_user)               # пользователь заблокировал бота

    active = await subscription_repo.list_active()

    assert {s.id for s in active} == {dou.id, djinni.id, both.id}


async def test_list_active_filters_by_source_and_loads_user(subscription_repo, user, create_subscription):
    dou = await create_subscription(user, sources=["dou"])
    await create_subscription(user, sources=["djinni"])
    both = await create_subscription(user, sources=["dou", "djinni"])

    for_dou = await subscription_repo.list_active("dou")

    assert {s.id for s in for_dou} == {dou.id, both.id}
    assert all(s.user.telegram_id == user.telegram_id for s in for_dou)   # пользователь подгружен сразу


async def test_set_active(subscription_repo, user, create_subscription, db_value):
    subscription = await create_subscription(user)

    assert await subscription_repo.set_active(subscription.id, False) is True
    assert await db_value(SubscriptionModel.is_active, SubscriptionModel.id == subscription.id) is False
    assert await subscription_repo.set_active(uuid4(), True) is False


async def test_delete_for_user_only_removes_own_subscription(
    subscription_repo, user, other_user, create_subscription
):
    subscription = await create_subscription(user)

    assert await subscription_repo.delete_for_user(subscription.id, other_user.id) is False
    assert await subscription_repo.exists(subscription.id) is True

    assert await subscription_repo.delete_for_user(subscription.id, user.id) is True
    assert await subscription_repo.exists(subscription.id) is False