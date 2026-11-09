from aiogram.fsm.state import State, StatesGroup


class Editor(StatesGroup):
    """Состояния, в которых бот ждёт от пользователя текст. Во всех остальных экранах только кнопки."""

    waiting_search = State()      # часть названия категории или города
    waiting_salary = State()      # минимальная зарплата
    waiting_keywords = State()    # ключевые слова
    waiting_exclude = State()     # исключаемые слова
