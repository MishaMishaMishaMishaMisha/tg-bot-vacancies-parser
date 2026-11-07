import pytest

from src.db.models import SubscriptionModel
from src.services import UserNotFoundError

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_register_creates_user(user_service):
    user = await user_service.register(100, username="ann", first_name="Ann", language_code="uk")

    assert user.id is not None
    assert (user.telegram_id, user.username, user.first_name, user.language_code) == (100, "ann", "Ann", "uk")
    assert user.is_active is True


async def test_register_updates_profile_and_reactivates_blocked_user(user_service):
    first = await user_service.register(100, username="old")
    await user_service.deactivate(100)

    again = await user_service.register(100, username="new")

    assert again.id == first.id
    assert again.username == "new"
    assert again.is_active is True
    assert await user_service.count_active() == 1


async def test_get_and_require(user_service):
    assert await user_service.get(100) is None
    with pytest.raises(UserNotFoundError):
        await user_service.require(100)

    registered = await user_service.register(100)

    assert (await user_service.get(100)).id == registered.id
    assert (await user_service.require(100)).id == registered.id


async def test_deactivate(user_service):
    await user_service.register(100)

    assert await user_service.deactivate(100) is True
    assert (await user_service.get(100)).is_active is False
    assert await user_service.deactivate(999) is False


async def test_delete_removes_user_together_with_subscriptions(user_service, subscribe, count_rows):
    await subscribe(100)

    assert await user_service.delete(100) is True
    assert await user_service.get(100) is None
    assert await count_rows(SubscriptionModel) == 0
    assert await user_service.delete(100) is False
