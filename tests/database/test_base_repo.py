"""CRUD из BaseRepository. Проверяем на UserRepository: самая простая таблица."""
from uuid import uuid4
 
import pytest
 
from src.db.models import UserModel
 
pytestmark = pytest.mark.asyncio(loop_scope="session")
 
async def test_create_assigns_id_and_get_returns_entity(user_repo):
    user = await user_repo.create(telegram_id=111, username="alice")
 
    assert user.id is not None
    assert await user_repo.get(user.id) is user
 
 
async def test_get_unknown_id_returns_none(user_repo):
    assert await user_repo.get(uuid4()) is None
 
 
async def test_get_many_returns_only_requested(user_repo, create_user):
    u1, _, u3 = [await create_user() for _ in range(3)]
 
    found = await user_repo.get_many([u1.id, u3.id])
 
    assert {u.id for u in found} == {u1.id, u3.id}
    assert await user_repo.get_many([]) == []
 
 
async def test_get_all_supports_order_by_limit_and_offset(user_repo, create_user):
    for telegram_id in (3, 1, 2):
        await create_user(telegram_id=telegram_id)
 
    ordered = await user_repo.get_all(order_by=UserModel.telegram_id)
    page = await user_repo.get_all(order_by=UserModel.telegram_id, limit=1, offset=1)
 
    assert [u.telegram_id for u in ordered] == [1, 2, 3]
    assert [u.telegram_id for u in page] == [2]
 
 
async def test_count_and_exists(user_repo, create_user):
    assert await user_repo.count() == 0
 
    user = await create_user()
    await create_user()
 
    assert await user_repo.count() == 2
    assert await user_repo.exists(user.id) is True
    assert await user_repo.exists(uuid4()) is False
 
 
async def test_add_and_add_many(user_repo):
    single = await user_repo.add(UserModel(telegram_id=1))
    many = await user_repo.add_many([UserModel(telegram_id=2), UserModel(telegram_id=3)])
 
    assert single.id is not None
    assert all(u.id is not None for u in many)
    assert await user_repo.count() == 3
 
 
async def test_update_changes_fields_in_db(user_repo, create_user, db_value):
    user = await create_user(username="old")
 
    updated = await user_repo.update(user, username="new", first_name="Nick")
 
    assert updated is user
    assert await db_value(UserModel.username, UserModel.id == user.id) == "new"
    assert await db_value(UserModel.first_name, UserModel.id == user.id) == "Nick"
 
 
async def test_update_by_id(user_repo, create_user):
    user = await create_user(language_code="uk")
 
    updated = await user_repo.update_by_id(user.id, language_code="en")
 
    assert updated.language_code == "en"
    assert await user_repo.update_by_id(uuid4(), language_code="en") is None
 
 
async def test_delete_removes_entity(user_repo, create_user):
    user = await create_user()
    user_id = user.id
 
    await user_repo.delete(user)
 
    assert await user_repo.exists(user_id) is False
 
 
async def test_delete_by_id(user_repo, create_user):
    user = await create_user()
 
    assert await user_repo.delete_by_id(user.id) is True
    assert await user_repo.delete_by_id(user.id) is False   # второй раз удалять уже нечего
    assert await user_repo.delete_by_id(uuid4()) is False