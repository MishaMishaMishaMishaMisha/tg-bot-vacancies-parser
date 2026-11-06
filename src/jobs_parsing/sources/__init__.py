from .base import JobSource, UnsupportedQuery, available_sources, create_source, register_source

# Импорт модулей регистрирует источники в реестре (декоратор @register_source).
from .dou import DouSource  # noqa: F401
from .djinni import DjinniSource  # noqa: F401

__all__ = [
    "JobSource",
    "UnsupportedQuery",
    "available_sources",
    "create_source",
    "register_source",
    "DouSource",
    "DjinniSource",
]
