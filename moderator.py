"""Основная логика модерации."""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import Message, User, Chat
from aiogram.exceptions import TelegramBadRequest

from src.filters.profanity_filter import profanity_filter
from src.database.connection import db
from config import settings

logger = logging.getLogger(__name__)


class Moderator:
    """Класс для модерации сообщений."""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.warnings: dict[tuple[int, int], int] = {}  # {(user_id, chat_id): warnings_count}
    
    async def check_message(self, message: Message) -> bool:
        """
        Проверяет сообщение на нарушение правил.
        
        Returns:
            bool: True если сообщение нарушает правила
        """
        if not message.text:
            return False
        
        # Проверяем на нецензурщину
        has_profanity, found_words = profanity_filter.contains_profanity(message.text)
        
        if has_profanity:
            logger.info(
                f"Найдена нецензурщина в сообщении {message.message_id} "
                f"от пользователя {message.from_user.id} в чате {message.chat.id}. "
                f"Найденные слова: {found_words}"
            )
            return True
        
        return False
    
    async def handle_violation(self, message: Message) -> bool:
        """
        Обрабатывает нарушение правил.
        
        Returns:
            bool: True если обработка прошла успешно
        """
        user = message.from_user
        chat = message.chat
        user_id = user.id
        chat_id = chat.id
        
        try:
            # Логируем сообщение в БД
            await db.log_message(
                message_id=message.message_id,
                user_id=user_id,
                chat_id=chat_id,
                message_text=message.text,
                username=user.username
            )
            
            # Проверяем, является ли отправитель администратором
            if await self._is_admin(user_id, chat_id):
                logger.debug(f"Пользователь {user_id} является администратором, пропускаем")
                return False
            
            # Удаляем сообщение
            if settings.DELETE_MESSAGES:
                deleted = await self.delete_message(message)
                if not deleted:
                    logger.warning(f"Не удалось удалить сообщение {message.message_id}")
            
            # Получаем текущую статистику пользователя
            stats = await db.get_user_stats(user_id, chat_id)
            current_warnings = stats.get('warnings_count', 0)
            
            # Обновляем статистику
            await db.update_user_stats(
                user_id=user_id,
                chat_id=chat_id,
                username=user.username,
                increment_deleted=1 if settings.DELETE_MESSAGES else 0
            )
            
            # Логируем действие
            await db.log_action(
                user_id=user_id,
                chat_id=chat_id,
                action_type='message_deleted',
                reason='Нецензурное выражение',
                message_text=message.text,
                username=user.username
            )
            
            # Проверяем количество предупреждений
            if settings.WARN_BEFORE_BAN > 0:
                # Увеличиваем количество предупреждений
                new_warnings_count = current_warnings + 1
                
                await db.update_user_stats(
                    user_id=user_id,
                    chat_id=chat_id,
                    increment_warnings=1
                )
                
                remaining_warnings = settings.WARN_BEFORE_BAN - new_warnings_count
                
                # Отправляем предупреждение
                if remaining_warnings > 0:
                    warning_text = (
                        f"⚠️ Предупреждение!\n\n"
                        f"Ваше сообщение было удалено за использование нецензурных выражений.\n"
                        f"Осталось предупреждений: {remaining_warnings}/{settings.WARN_BEFORE_BAN}\n"
                        f"После превышения лимита вы будете заблокированы."
                    )
                else:
                    warning_text = (
                        f"🚫 Последнее предупреждение!\n\n"
                        f"Вы получили максимальное количество предупреждений. "
                        f"Следующее нарушение приведет к блокировке."
                    )
                
                try:
                    await message.answer(warning_text)
                except Exception as e:
                    logger.error(f"Ошибка отправки предупреждения: {e}")
                
                # Баним если превышен лимит
                if new_warnings_count >= settings.WARN_BEFORE_BAN and settings.BAN_USERS:
                    await self.ban_user(user_id, chat_id, "Превышен лимит предупреждений")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обработки нарушения: {e}")
            return False
    
    async def delete_message(self, message: Message) -> bool:
        """Удаляет сообщение."""
        try:
            await message.delete()
            await db.mark_message_deleted(message.message_id, message.chat.id)
            logger.info(f"Сообщение {message.message_id} удалено из чата {message.chat.id}")
            return True
        except TelegramBadRequest as e:
            logger.error(f"Не удалось удалить сообщение: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            return False
    
    async def ban_user(self, user_id: int, chat_id: int, reason: str = "Нарушение правил"):
        """Блокирует пользователя в чате."""
        try:
            # Получаем информацию о пользователе для логирования
            stats = await db.get_user_stats(user_id, chat_id)
            username = stats.get('username', 'Unknown')
            
            # Баним пользователя
            await self.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=None  # Бан навсегда
            )
            
            # Обновляем статистику
            await db.update_user_stats(
                user_id=user_id,
                chat_id=chat_id,
                set_banned=True
            )
            
            # Логируем действие
            await db.log_action(
                user_id=user_id,
                chat_id=chat_id,
                action_type='ban',
                reason=reason,
                username=username
            )
            
            logger.info(f"Пользователь {user_id} заблокирован в чате {chat_id}. Причина: {reason}")
            
            # Отправляем уведомление в чат
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 Пользователь @{username or f'ID{user_id}'} был заблокирован.\n"
                         f"Причина: {reason}"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о бане: {e}")
                
        except TelegramBadRequest as e:
            logger.error(f"Не удалось заблокировать пользователя {user_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка блокировки пользователя: {e}")
    
    async def unban_user(self, user_id: int, chat_id: int):
        """Разблокирует пользователя в чате."""
        try:
            await self.bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                only_if_banned=True
            )
            
            # Обновляем статистику
            await db.update_user_stats(
                user_id=user_id,
                chat_id=chat_id,
                set_banned=False
            )
            
            # Логируем действие
            await db.log_action(
                user_id=user_id,
                chat_id=chat_id,
                action_type='unban',
                reason='Разблокировка администратором'
            )
            
            logger.info(f"Пользователь {user_id} разблокирован в чате {chat_id}")
            
        except Exception as e:
            logger.error(f"Ошибка разблокировки пользователя: {e}")
    
    async def _is_admin(self, user_id: int, chat_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        try:
            member = await self.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            return member.status in ['administrator', 'creator']
        except Exception as e:
            logger.error(f"Ошибка проверки прав администратора: {e}")
            return False

