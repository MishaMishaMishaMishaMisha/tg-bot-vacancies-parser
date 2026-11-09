"""Текст сообщения с вакансией для Telegram."""
from __future__ import annotations

import re

from src.services.jobs import Vacancy

from .texts import SOURCE_TITLES, esc

OPEN_LINK_TEXT = "Відкрити вакансію"

# Сколько символов описания добавлять в сообщение. 0 означает «не добавлять»:
# по требованиям в сообщении только название, компания, локация, зарплата, категория и ссылка.
DESCRIPTION_CHARS = 0


def format_vacancy_message(vacancy: Vacancy) -> str:
    """Название, затем компания, локация, зарплата и категория (только если указаны) и ссылка."""
    lines = [f"<b>{esc(vacancy.title)}</b>"]

    if vacancy.company:
        lines.append(f"🏢 {esc(vacancy.company)}")
    if vacancy.locations:
        lines.append(f"📍 {esc(', '.join(vacancy.locations))}")
    if vacancy.salary:
        lines.append(f"💰 {esc(vacancy.salary)}")
    if vacancy.category:
        lines.append(f"🏷 {esc(vacancy.category)}")

    if DESCRIPTION_CHARS and vacancy.text:
        text = re.sub(r"\s+", " ", vacancy.text).strip()
        if len(text) > DESCRIPTION_CHARS:
            text = (text[:DESCRIPTION_CHARS].rsplit(" ", 1)[0] or text[:DESCRIPTION_CHARS]).rstrip(",.;:- ") + "…"
        lines += ["", esc(text)]

    source = SOURCE_TITLES.get(vacancy.source, vacancy.source)
    url = vacancy.url.replace("&", "&amp;").replace('"', "&quot;")
    lines += ["", f'🔗 <a href="{url}">{OPEN_LINK_TEXT}</a> · {esc(source)}']
    return "\n".join(lines)
