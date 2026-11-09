from aiogram.filters.callback_data import CallbackData


class Action(CallbackData, prefix="a"):
    """Единственный формат callback_data во всём боте.

    a  действие: menu, edit, screen, toggle, pick, page, clear, search, save, cancel, ...
    f  поле фильтра или экран: categories, experiences, editor, ...
    v  значение: "1-3", "remote" или номер элемента в длинном списке
    p  номер страницы

    Всё короткое: в callback_data у Telegram лимит 64 байта, поэтому названия категорий в нём
    не передаются, только их номера в списке, сохранённом в состоянии диалога.
    """

    a: str
    f: str = ""
    v: str = ""
    p: int = 0
