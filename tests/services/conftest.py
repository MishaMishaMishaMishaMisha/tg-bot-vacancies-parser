"""Фикстуры для тестов сервисов.

Как устроена изоляция: сервисы открывают UnitOfWork и делают commit, поэтому обычный откат сессии,
как в тестах репозиториев, тут не сработал бы. SavepointUnitOfWork работает на общей сессии `db_session`
и вместо commit/rollback использует SAVEPOINT: сервисы ведут себя как в проде, а в конце теста
внешняя транзакция откатывается и в БД ничего не остаётся.

Сайты и Telegram заменены фейками: тесты не ходят в сеть.
"""
import itertools

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from src.db.models import NotificationModel, UserModel, VacancyModel
from src.db.repositories import (
    NotificationRepository,
    SubscriptionRepository,
    UserRepository,
    VacancyRepository,
)
from src.services import (
    FilterCatalogService,
    NotificationService,
    NotifierError,
    PollingService,
    RetryAfterError,
    ServiceSettings,
    SubscriptionFilters,
    SubscriptionService,
    UserBlockedError,
    UserService,
)
from src.services.jobs import FilterOptions, JobSource, SearchQuery, UnsupportedQuery, Vacancy
from src.services.query_builder import SubscriptionQueryBuilder
from src.services.unit_of_work import UnitOfWork


# ============================================================ БД: изоляция и вспомогательные запросы

class SavepointUnitOfWork(UnitOfWork):
    """UnitOfWork для тестов: общая сессия, commit = RELEASE SAVEPOINT, выход без commit = ROLLBACK TO SAVEPOINT."""

    def __init__(self, session):
        self.session = session   # super().__init__ не вызываем: собственная сессия не нужна

    async def __aenter__(self):
        self._transaction = await self.session.begin_nested()
        self.users = UserRepository(self.session)
        self.subscriptions = SubscriptionRepository(self.session)
        self.vacancies = VacancyRepository(self.session)
        self.notifications = NotificationRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._transaction.is_active:   # исключение или не было commit
            await self._transaction.rollback()

    async def commit(self):
        await self._transaction.commit()

    async def rollback(self):
        await self._transaction.rollback()


@pytest.fixture
def uow_factory(db_session):
    return lambda: SavepointUnitOfWork(db_session)


@pytest.fixture
def db_notifications(db_session):
    """await db_notifications() -> [(telegram_id, id вакансии на сайте, статус)]; можно отфильтровать по статусу."""

    async def _get(status=None):
        stmt = (
            select(UserModel.telegram_id, VacancyModel.external_id, NotificationModel.status)
            .select_from(NotificationModel)
            .join(UserModel, NotificationModel.user_id == UserModel.id)
            .join(VacancyModel, NotificationModel.vacancy_id == VacancyModel.id)
        )
        if status is not None:
            stmt = stmt.where(NotificationModel.status == status)
        return [tuple(row) for row in (await db_session.execute(stmt)).all()]

    return _get


@pytest.fixture
def count_rows(db_session):
    """await count_rows(SubscriptionModel) -> число строк в таблице."""

    async def _count(model):
        return await db_session.scalar(select(func.count()).select_from(model))

    return _count


@pytest.fixture
def deactivate_in_db(db_session):
    """Выключить пользователя напрямую в БД, в обход UserService.deactivate (он заодно чистит очередь)."""

    async def _deactivate(user_id):
        await UserRepository(db_session).set_active(user_id, False)

    return _deactivate


# ============================================================ фейковые сайты и Telegram

class FakeSource(JobSource):
    """Сайт вакансий без сети.

    vacancies           вакансии «на сайте» по категориям; добавляйте через add()
    fetch_calls         какие запросы к сайту были сделаны
    fail                True: fetch бросает ошибку
    fail_refresh        True: обновление фильтров бросает ошибку
    supports_extra_filters=False: сайт не умеет english/min_salary/region/relocation (как DOU)
    """

    def __init__(self, name, *, categories=("Python", "Java"), cities=("Київ",), english_levels=(),
                 supports_extra_filters=True):
        super().__init__(client=object())   # HTTP-клиент не нужен
        self.name = name
        groups = {}
        if english_levels:
            groups["english_level"] = [{"value": v, "label": label} for v, label in english_levels]
        self._options = FilterOptions(categories=list(categories), cities=list(cities), groups=groups)
        self.supports_extra_filters = supports_extra_filters
        self.vacancies = {}
        self.fetch_calls = []
        self.fail = False
        self.fail_refresh = False

    def add(self, category, *vacancies):
        self.vacancies.setdefault(category, []).extend(vacancies)

    async def fetch(self, query=None):
        self.fetch_calls.append(query)
        if self.fail:
            raise RuntimeError("site is down")
        return list(self.vacancies.get(query.category, []))

    async def fetch_filter_options(self):
        return self._options

    async def get_filter_options(self, refresh=False):
        # Переопределено, чтобы не читать и не перезаписывать настоящие файлы в cache/
        if refresh and self.fail_refresh:
            raise RuntimeError("refresh failed")
        return self._options

    async def validate_query(self, query):
        if not self.supports_extra_filters and (query.english or query.min_salary or query.region or query.relocation):
            raise UnsupportedQuery(f"{self.name}: не поддерживает фильтры english/min_salary/region/relocation")


class FakeNotifier:
    """Вместо Telegram. Поведением управляют множества и счётчики."""

    def __init__(self):
        self.sent = []            # [(telegram_id, Vacancy)]
        self.blocked = set()      # эти пользователи заблокировали бота
        self.rate_limited = {}    # telegram_id -> сколько раз ответить «слишком часто»
        self.failing = set()      # для них отправка всегда падает

    async def send_vacancy(self, telegram_id, vacancy):
        if telegram_id in self.blocked:
            raise UserBlockedError("bot was blocked by the user")
        if self.rate_limited.get(telegram_id, 0) > 0:
            self.rate_limited[telegram_id] -= 1
            raise RetryAfterError(0)
        if telegram_id in self.failing:
            raise NotifierError("telegram is unavailable")
        self.sent.append((telegram_id, vacancy))

    def recipients(self, vacancy_id):
        """Кому ушла вакансия, по возрастанию telegram_id."""
        return sorted(t for t, v in self.sent if v.id == vacancy_id)

    def vacancy_ids(self, telegram_id):
        return sorted(v.id for t, v in self.sent if t == telegram_id)


@pytest.fixture
def settings():
    return ServiceSettings(send_interval_seconds=0, max_subscriptions_per_user=3, max_queries_per_subscription=10)


@pytest.fixture
def dou_source():
    return FakeSource("dou", categories=["Python", "Java"], cities=["Київ", "Львів"], supports_extra_filters=False)


@pytest.fixture
def djinni_source():
    return FakeSource(
        "djinni",
        categories=["Python", "Design"],
        cities=["Київ"],
        english_levels=[("basic", "Beginner/Elementary"), ("intermediate", "Intermediate")],
    )


@pytest.fixture
def make_source():
    """make_source("name", categories=[...], ...) -> FakeSource: для тестов с нестандартными сайтами."""
    return FakeSource


@pytest.fixture
def notifier():
    return FakeNotifier()


# ============================================================ сервисы

@pytest.fixture
def sources(dou_source, djinni_source):
    return {"dou": dou_source, "djinni": djinni_source}


@pytest.fixture
def builder(settings):
    return SubscriptionQueryBuilder(settings.max_queries_per_subscription)


@pytest.fixture
def user_service(uow_factory):
    return UserService(uow_factory)


@pytest.fixture
def polling_service(sources, uow_factory, builder, settings):
    return PollingService(sources, uow_factory, builder, settings)


@pytest.fixture
def subscription_service(uow_factory, builder, sources, settings, polling_service):
    # как в проде: PollingService «засевает» подписку сразу после создания
    return SubscriptionService(uow_factory, builder, sources, settings, seeder=polling_service)


@pytest.fixture
def delivery_service(notifier, uow_factory, settings):
    return NotificationService(notifier, uow_factory, settings)


@pytest.fixture
def catalog_service(sources, settings):
    return FilterCatalogService(sources, settings)


# ============================================================ фабрики данных

@pytest.fixture
def make_vacancy():
    counter = itertools.count(1)

    def _make(source="dou", *, id=None, title=None, category="Python", **extra):
        id = id or str(next(counter))
        return Vacancy(
            source=source,
            id=id,
            title=title or f"Python Developer #{id}",
            url=f"https://example.com/{source}/{id}",
            category=category,
            **extra,
        )

    return _make


@pytest_asyncio.fixture
async def subscribe(user_service, subscription_service):
    """await subscribe(telegram_id, **фильтры): регистрирует пользователя и создаёт подписку (по умолчанию DOU, Python)."""

    async def _subscribe(telegram_id, **filters):
        await user_service.register(telegram_id, username=f"user{telegram_id}")
        values = {"sources": ["dou"], "categories": ["Python"]}
        values.update(filters)
        result = await subscription_service.create(telegram_id, SubscriptionFilters(**values))
        return result.subscription

    return _subscribe


@pytest_asyncio.fixture
async def publish(polling_service, dou_source, make_vacancy):
    """await publish(): на DOU появилась новая вакансия по Python, выполнен цикл опроса."""

    async def _publish(title=None):
        vacancy = make_vacancy("dou", title=title)
        dou_source.add("Python", vacancy)
        await polling_service.run_cycle()
        return vacancy

    return _publish
