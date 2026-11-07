"""Тест всего процесса через ServiceContainer, как его будет вызывать бот:

    регистрация пользователя -> сохранение фильтров -> запросы к сайтам -> уведомление о совпадениях

Сайты и Telegram заменены фейками, БД настоящая (с откатом после теста).
"""
import pytest
import pytest_asyncio

from src.db.models import NotificationStatus
from src.services import ServiceContainer, SubscriptionFilters, format_vacancy
from src.services.jobs import Employment, Experience, SearchQuery

pytestmark = pytest.mark.asyncio(loop_scope="session")

SENT = NotificationStatus.SENT
SKIPPED = NotificationStatus.SKIPPED
ANN = 777


@pytest_asyncio.fixture
async def container(monkeypatch, uow_factory, dou_source, djinni_source, notifier, settings):
    fake_sites = {"dou": dou_source, "djinni": djinni_source}
    monkeypatch.setattr("src.services.container.create_source", lambda name: fake_sites[name])
    return ServiceContainer(notifier, settings=settings, uow_factory=uow_factory, source_names=["dou", "djinni"])


async def test_user_is_notified_about_new_matching_vacancy(
    container, dou_source, djinni_source, notifier, make_vacancy, db_notifications
):
    # 1. Регистрация
    user = await container.users.register(ANN, username="ann", first_name="Ann", language_code="uk")
    assert user.is_active is True

    # 2. Сохранение фильтров. На DOU уже висит вакансия: после создания подписки она не должна прийти.
    old_vacancy = make_vacancy("dou", title="Python Developer (old)")
    dou_source.add("Python", old_vacancy)
    result = await container.subscriptions.create(
        ANN,
        SubscriptionFilters(
            sources=["dou", "djinni"],
            categories=["Python"],
            experiences=["1-3"],
            employments=["remote"],
            exclude_keywords=["senior"],
        ),
    )
    assert result.subscription.is_seeded is True
    assert result.warnings == []

    # 3. Сайты получили запросы, собранные из фильтров пользователя
    expected_query = SearchQuery(category="Python", experience=Experience.Y1_3, employment=Employment.REMOTE)
    assert dou_source.fetch_calls == [expected_query]
    assert djinni_source.fetch_calls == [expected_query]

    # Пока на сайтах ничего нового, пользователь ничего не получает
    await container.scheduler.run_once()
    assert notifier.sent == []

    # 4. На сайтах появились вакансии: две подходящие и одна с исключённым словом
    new_on_dou = make_vacancy("dou", title="Python Developer (Django)")
    new_on_djinni = make_vacancy("djinni", title="Backend Python Engineer")
    excluded = make_vacancy("dou", title="Senior Python Developer")
    dou_source.add("Python", new_on_dou, excluded)
    djinni_source.add("Python", new_on_djinni)

    cycle, delivery = await container.scheduler.run_once()

    # 5. Пользователь получил ровно две подходящие вакансии
    assert cycle.new_vacancies == 3   # все три сохранены в базе
    assert delivery.sent == 2
    assert notifier.vacancy_ids(ANN) == sorted([new_on_dou.id, new_on_djinni.id])
    assert excluded.id not in notifier.vacancy_ids(ANN)
    sent_messages = [format_vacancy(vacancy) for _, vacancy in notifier.sent]
    assert all(vacancy.url in message for (_, vacancy), message in zip(notifier.sent, sent_messages))

    statuses = {(vacancy_id, status) for _, vacancy_id, status in await db_notifications()}
    assert statuses == {(old_vacancy.id, SKIPPED), (new_on_dou.id, SENT), (new_on_djinni.id, SENT)}

    # 6. Следующий цикл ничего не дублирует
    cycle, delivery = await container.scheduler.run_once()
    assert cycle.new_vacancies == 0
    assert delivery.sent == 0
    assert len(notifier.sent) == 2


async def test_nothing_is_sent_when_nothing_new_matches(container, dou_source, notifier, make_vacancy):
    await container.users.register(ANN)
    dou_source.add("Python", make_vacancy("dou"))   # уже была на момент подписки
    await container.subscriptions.create(
        ANN, SubscriptionFilters(sources=["dou"], categories=["Python"], keywords=["django"])
    )

    dou_source.add("Python", make_vacancy("dou", title="Python Flask Developer"))   # новая, но без слова django
    dou_source.add("Java", make_vacancy("dou", title="Java Django Developer", category="Java"))   # другая категория

    cycle, delivery = await container.scheduler.run_once()

    assert cycle.new_vacancies == 1
    assert delivery.sent == 0
    assert notifier.sent == []


async def test_users_with_same_filters_share_requests_and_all_get_notified(
    container, dou_source, notifier, make_vacancy
):
    for telegram_id in (1, 2, 3):
        await container.users.register(telegram_id)
        await container.subscriptions.create(telegram_id, SubscriptionFilters(sources=["dou"], categories=["Python"]))
    dou_source.fetch_calls.clear()
    vacancy = make_vacancy("dou")
    dou_source.add("Python", vacancy)

    await container.scheduler.run_once()

    assert len(dou_source.fetch_calls) == 1   # один запрос на троих
    assert notifier.recipients(vacancy.id) == [1, 2, 3]


async def test_user_who_blocked_the_bot_is_switched_off_and_resumes_after_start(
    container, dou_source, notifier, make_vacancy
):
    await container.users.register(ANN)
    await container.subscriptions.create(ANN, SubscriptionFilters(sources=["dou"], categories=["Python"]))
    notifier.blocked.add(ANN)
    dou_source.add("Python", make_vacancy("dou"))

    _, delivery = await container.scheduler.run_once()

    assert delivery.users_deactivated == 1
    assert (await container.users.get(ANN)).is_active is False

    # Пользователь снова нажал /start: подписка сохранилась, вакансия за время блокировки не придёт
    notifier.blocked.clear()
    await container.users.register(ANN)
    await container.scheduler.run_once()
    assert notifier.sent == []

    after_return = make_vacancy("dou")
    dou_source.add("Python", after_return)
    await container.scheduler.run_once()

    assert notifier.vacancy_ids(ANN) == [after_return.id]
