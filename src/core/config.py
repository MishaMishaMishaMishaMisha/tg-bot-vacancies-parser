from pydantic_settings import BaseSettings, SettingsConfigDict
from dataclasses import dataclass

from src.core.paths import ENV_FILE_PATH


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Настройки сервисов"""

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

class DBSettings(BaseSettings):
    
    HOST: str
    PORT: int
    DB: str # name
    USER: str
    PASSWORD: str
    
    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DB}"
    
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH,
                                      env_prefix="POSTGRES_",
                                      extra="ignore")


class TelegramSettings(BaseSettings):
    
    API_TOKEN: str
    
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH,
                                      env_prefix="TELEGRAM_",
                                      extra="ignore")


class ProjectSettings(BaseSettings):
    
    MODE: str
    
    db: DBSettings = DBSettings()
    tg: TelegramSettings = TelegramSettings()
    
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, extra="ignore")
    
    
settings = ProjectSettings()


