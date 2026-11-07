import pytest

from src.services.jobs import Vacancy
from src.services.matching import passes_local_filters

VACANCY = Vacancy(
    source="dou",
    id="1",
    title="Python Django Developer",
    url="https://example.com/1",
    company="Acme",
    category="Python",
    tags=("Remote",),
    text="Flask and FastAPI experience",
)


@pytest.mark.parametrize(
    "keywords, exclude, expected",
    [
        ([], [], True),                              # фильтров нет
        (["django"], [], True),                      # слово в названии
        (["fastapi"], [], True),                     # в описании
        (["remote"], [], True),                      # в метках
        (["acme"], [], True),                        # в названии компании
        (["DJANGO"], [], True),                      # регистр не важен
        (["java", "rust"], [], False),               # ни одного слова
        (["java", "django"], [], True),              # достаточно одного из слов
        ([], ["django"], False),                     # исключённое слово есть
        ([], ["java"], True),                        # исключённого слова нет
        (["python"], ["flask"], False),              # исключение сильнее ключевых слов
    ],
)
def test_passes_local_filters(keywords, exclude, expected):
    assert passes_local_filters(VACANCY, keywords, exclude) is expected
