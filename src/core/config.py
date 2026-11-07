from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.paths import ENV_FILE_PATH


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