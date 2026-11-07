"""Исключения сервисного слоя. Бот ловит их и показывает пользователю понятное сообщение."""
from __future__ import annotations


class ServiceError(Exception):
    """Базовое исключение всех сервисов."""


class ValidationError(ServiceError):
    """Некорректные или невыполнимые фильтры. В `warnings` лежат подробности (см. QueryWarning)."""

    def __init__(self, message: str, *, warnings: list | None = None) -> None:
        super().__init__(message)
        self.warnings = warnings or []


class UserNotFoundError(ServiceError):
    """Пользователь не зарегистрирован (не было /start)."""


class SubscriptionNotFoundError(ServiceError):
    """Подписки нет или она принадлежит другому пользователю."""


class SubscriptionLimitError(ServiceError):
    """У пользователя уже максимальное число подписок."""
