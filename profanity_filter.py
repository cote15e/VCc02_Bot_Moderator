"""Фильтр нецензурных выражений."""
import re
from typing import List, Tuple


class ProfanityFilter:
    """Класс для фильтрации нецензурных выражений."""
    
    def __init__(self):
        # Список нецензурных слов (русский и английский)
        # В реальном проекте лучше хранить в БД или файле
        self.bad_words = [
            # Русские матерные слова (заменены на примеры)
            'блять', 'блядь', 'ебан', 'ебать', 'хуй', 'хуя', 'пизд', 'ебл',
            # Английские
            'fuck', 'shit', 'damn', 'bitch', 'asshole', 'cunt',
            # Попытки обхода фильтра
            'бл*ть', 'бл@ть', 'бля***', 'ху*', 'п*зд',
            # Другие варианты
            'еблан', 'долбоёб', 'мразь', 'говно'
        ]
        
        # Создаем паттерны для поиска
        self.patterns = []
        for word in self.bad_words:
            # Заменяем некоторые символы на паттерны
            pattern = word.lower()
            pattern = pattern.replace('*', r'\S*')
            pattern = pattern.replace('@', r'[а@a]')
            pattern = re.escape(pattern)
            # Учитываем замену букв на похожие
            pattern = pattern.replace(r'\*', r'\S*')
            self.patterns.append(re.compile(pattern, re.IGNORECASE))
    
    def contains_profanity(self, text: str) -> Tuple[bool, List[str]]:
        """
        Проверяет текст на наличие нецензурных выражений.
        
        Returns:
            Tuple[bool, List[str]]: (содержит ли мат, список найденных слов)
        """
        if not text:
            return False, []
        
        text_lower = text.lower()
        found_words = []
        
        # Проверяем по паттернам
        for pattern in self.patterns:
            matches = pattern.findall(text_lower)
            if matches:
                found_words.extend(matches)
        
        # Также проверяем простым поиском подстроки
        for word in self.bad_words:
            if word.lower() in text_lower:
                if word not in found_words:
                    found_words.append(word)
        
        return len(found_words) > 0, found_words
    
    def clean_text(self, text: str, replacement: str = "***") -> str:
        """Очищает текст от нецензурных выражений."""
        if not text:
            return text
        
        cleaned_text = text
        for word in self.bad_words:
            # Заменяем слово на replacement
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            cleaned_text = pattern.sub(replacement, cleaned_text)
        
        return cleaned_text


# Глобальный экземпляр фильтра
profanity_filter = ProfanityFilter()

