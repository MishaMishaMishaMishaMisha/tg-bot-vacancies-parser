from uuid import uuid4

import pytest

from src.db.models import UserModel

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_get_by_telegram_id(user_repo, create_user):
    user = await create_user(telegram_id=42)

    assert (await user_repo.get_by_telegram_id(42)).id == user.id
    assert await user_repo.get_by_telegram_id(43) is None


async def test_upsert_from_telegram_creates_new_user(user_repo):
    user = await user_repo.upsert_from_telegram(
        777, username="alice", first_name="Alice", language_code="uk"
    )

    assert user.id is not None
    assert (user.telegram_id, user.username, user.first_name, user.language_code) == (777, "alice", "Alice", "uk")
    assert user.is_active is True


async def test_upsert_from_telegram_updates_existing_user(user_repo):
    first = await user_repo.upsert_from_telegram(777, username="old_name")

    second = await user_repo.upsert_from_telegram(777, username="new_name", first_name="Alice")

    assert second.id == first.id
    assert second.username == "new_name"
    assert second.first_name == "Alice"
    assert await user_repo.count() == 1


async def test_upsert_from_telegram_reactivates_user(user_repo, create_user):
    user = await create_user(telegram_id=555, is_active=False)

    result = await user_repo.upsert_from_telegram(555)

    assert result.id == user.id
    assert result.is_active is True


async def test_set_active(user_repo, create_user, db_value):
    user = await create_user()

    assert await user_repo.set_active(user.id, False) is True
    assert await db_value(UserModel.is_active, UserModel.id == user.id) is False
    assert await user_repo.set_active(uuid4(), True) is False


async def test_set_active_by_telegram_id(user_repo, create_user, db_value):
    user = await create_user(telegram_id=321)

    assert await user_repo.set_active_by_telegram_id(321, False) is True
    assert await db_value(UserModel.is_active, UserModel.id == user.id) is False
    assert await user_repo.set_active_by_telegram_id(999_999, False) is False


async def test_list_active_and_count_active(user_repo, create_user):
    active_1 = await create_user()
    active_2 = await create_user()
    await create_user(is_active=False)

    active = await user_repo.list_active()

    assert {u.id for u in active} == {active_1.id, active_2.id}
    assert len(await user_repo.list_active(limit=1)) == 1
    assert await user_repo.count_active() == 2


async def test_get_with_subscriptions_loads_subscriptions(user_repo, user, create_subscription):
    await create_subscription(user)
    await create_subscription(user, name="Java")

    loaded = await user_repo.get_with_subscriptions(user.id)

    assert len(loaded.subscriptions) == 2   # без «ленивой» загрузки: связь уже подгружена
    assert await user_repo.get_with_subscriptions(uuid4()) is None