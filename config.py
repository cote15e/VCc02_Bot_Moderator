"""Конфигурация бота."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Telegram Bot
    BOT_TOKEN: str
    
    # Database (PostgreSQL)
    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/bot.log"
    
    # Moderation settings
    DELETE_MESSAGES: bool = True
    BAN_USERS: bool = True
    WARN_BEFORE_BAN: int = 3  # Количество предупреждений до бана
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Глобальный экземпляр настроек
settings = Settings()

