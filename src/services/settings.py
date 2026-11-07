from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Настройки сервисов. Значения по умолчанию можно переопределить из вашего src/core/config.py."""

    # Опрос сайтов
    poll_interval_seconds: float = 600          # как часто опрашивать сайты
    gap_warning_threshold: int = 20             # предупреждать, если в выдаче столько вакансий и все новые
    filters_refresh_interval_seconds: float = 24 * 3600   # как часто обновлять списки фильтров сайтов

    # Ограничения для пользователей
    max_subscriptions_per_user: int = 5
    max_queries_per_subscription: int = 30      # комбинации фильтров = запросы к каждому сайту
    max_keywords: int = 20
    max_keyword_length: int = 50
    max_salary: int = 10_000                    # предел ползунка зарплаты на Djinni, $

    # Отправка уведомлений
    delivery_batch_size: int = 100
    send_interval_seconds: float = 0.1          # пауза между сообщениями (лимиты Telegram)
    max_delivery_attempts: int = 3
