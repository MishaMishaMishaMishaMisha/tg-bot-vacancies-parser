import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
 
import pytest
import pytest_asyncio
from sqlalchemy import select
 
from src.db.db_connection import async_engine, async_session_factory
from src.db.models import Base
from src.db.repositories import (
    NotificationRepository,
    SubscriptionRepository,
    UserRepository,
    VacancyRepository,
)


# создание и очистка таблиц в бд
@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_and_drop_tables():
    
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        

# бд сессия
@pytest_asyncio.fixture
async def db_session():
    async with async_session_factory() as session:
        yield session
        

#############


# Изоляция тестов: репозитории не делают commit, а db_session при выходе закрывает сессию,
# то есть откатывает транзакцию. Поэтому данные одного теста не видны другому и отдельная
# очистка таблиц не нужна. Главное: в тестах не вызывать db_session.commit().
 
_counter = itertools.count(1)
 
 
@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)
 
 
# ---- репозитории
@pytest.fixture
def user_repo(db_session) -> UserRepository:
    return UserRepository(db_session)
 
 
@pytest.fixture
def subscription_repo(db_session) -> SubscriptionRepository:
    return SubscriptionRepository(db_session)
 
 
@pytest.fixture
def vacancy_repo(db_session) -> VacancyRepository:
    return VacancyRepository(db_session)
 
 
@pytest.fixture
def notification_repo(db_session) -> NotificationRepository:
    return NotificationRepository(db_session)
 
 
# ---- чтение «как есть» из БД (в обход объектов в памяти сессии)
@pytest.fixture
def db_value(db_session):
    """await db_value(UserModel.username, UserModel.id == user.id)"""
 
    async def _get(column, *conditions):
        return await db_session.scalar(select(column).where(*conditions))
 
    return _get
 
 
# ---- фабрики сущностей: каждая принимает overrides и создаёт запись через репозиторий
@pytest_asyncio.fixture
async def create_user(user_repo):
    async def _create(**overrides):
        n = next(_counter)
        values = {
            "telegram_id": 10_000 + n,
            "username": f"user{n}",
            "first_name": f"User {n}",
            "language_code": "uk",
        }
        values.update(overrides)
        return await user_repo.create(**values)
 
    return _create
 
 
@pytest_asyncio.fixture
async def create_subscription(subscription_repo):
    async def _create(user, **overrides):
        values = {
            "user_id": user.id,
            "name": "Python",
            "sources": ["dou"],
            "categories": ["Python"],
        }
        values.update(overrides)
        return await subscription_repo.create(**values)
 
    return _create
 
 
@pytest_asyncio.fixture
async def create_vacancy(vacancy_repo):
    async def _create(**overrides):
        n = next(_counter)
        values = {
            "source": "dou",
            "external_id": str(100_000 + n),
            "title": f"Python Developer #{n}",
        }
        values.update(overrides)
        values.setdefault("url", f"https://example.com/{values['source']}/{values['external_id']}")
        return await vacancy_repo.create(**values)
 
    return _create
 
 
@pytest_asyncio.fixture
async def create_notification(notification_repo):
    async def _create(user, vacancy, **overrides):
        values = {"user_id": user.id, "vacancy_id": vacancy.id}
        values.update(overrides)
        return await notification_repo.create(**values)
 
    return _create
 
 
# ---- готовые сущности
@pytest_asyncio.fixture
async def user(create_user):
    return await create_user()
 
 
@pytest_asyncio.fixture
async def other_user(create_user):
    return await create_user()
 
 
# ---- «доменная» вакансия для VacancyRepository.upsert_many
@dataclass(frozen=True)
class DomainVacancyStub:
    """Те же поля, что у вакансии, которую возвращают парсеры сайтов.
 
    upsert_many читает только эти атрибуты, поэтому тестам не нужен настоящий класс.
    Если хотите, замените заглушку импортом вашего доменного Vacancy.
    """
 
    source: str
    id: str
    title: str
    url: str
    company: str | None = "ACME"
    category: str | None = "Python"
    locations: tuple[str, ...] = ("Київ",)
    salary: str | None = None
    published: datetime | None = None
    tags: tuple[str, ...] = ()
    text: str = "Опис вакансії"
 
 
@pytest.fixture
def make_domain_vacancy():
    def _make(**overrides) -> DomainVacancyStub:
        n = next(_counter)
        values = {"source": "dou", "id": str(900_000 + n), "title": f"Python Developer #{n}"}
        values.update(overrides)
        values.setdefault("url", f"https://example.com/{values['source']}/{values['id']}")
        return DomainVacancyStub(**values)
 
    return _make