"""Локальные фильтры: проверка вакансии по ключевым словам уже после получения с сайта."""
from __future__ import annotations

from typing import Sequence

from .jobs import Vacancy


def passes_local_filters(
    vacancy: Vacancy, keywords: Sequence[str], exclude_keywords: Sequence[str]
) -> bool:
    """keywords: должно встретиться хотя бы одно слово (если список не пуст).
    exclude_keywords: не должно встретиться ни одного.
    Ищем в названии, компании, категории, метках и описании, без учёта регистра.
    """
    if not keywords and not exclude_keywords:
        return True

    parts = [vacancy.title, vacancy.company, vacancy.category, vacancy.text, *vacancy.tags]
    haystack = " ".join(part for part in parts if part).casefold()

    if any(word.casefold() in haystack for word in exclude_keywords):
        return False
    if keywords and not any(word.casefold() in haystack for word in keywords):
        return False
    return True
