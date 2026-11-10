
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import feedparser
from bs4 import BeautifulSoup

from ..models import Employment, Experience, FilterOptions, SearchQuery, Vacancy
from ..utils import casefold_key, normalize
from .base import JobSource, UnsupportedQuery, register_source


log = logging.getLogger(__name__)

FEED_URL = "https://jobs.dou.ua/vacancies/feeds/"
LISTING_URL = "https://jobs.dou.ua/vacancies/"

# Пометки в заголовке вакансии.
LOCATION_MARKERS = frozenset({"віддалено", "за кордоном"})

_VACANCY_ID_RE = re.compile(r"/vacancies/(\d+)/")


class DouFeedParser:
    """Разбор RSS-ленты DOU."""

    @staticmethod
    def split_title(raw: str, places: frozenset[str]) -> tuple[str, str | None, list[str]]:
        """'Product Manager в Velrio, Київ, віддалено' -> (название, компания, локации).

        С конца отщепляем всё, что есть в `places` (города и пометки);
        то, что осталось, считаем названием компании.
        Сравнение идёт по нормализованным строкам, поэтому неразрывные пробелы,
        невидимые символы и разный регистр не мешают.
        """
        raw = normalize(raw)
        if " в " not in raw:
            return raw, None, []
        title, tail = raw.rsplit(" в ", 1)

        known = {casefold_key(p) for p in places}
        parts = [p.strip() for p in tail.split(",")]
        locations: list[str] = []
        while len(parts) > 1 and casefold_key(parts[-1]) in known:
            locations.insert(0, parts.pop())

        company = ", ".join(parts)
        if len(parts) > 1:
            # Либо у компании запятая в названии, либо город, которого нет в списке.
            log.debug("DOU: в названии компании остались запятые: %r", company)
        return title.strip(), company, locations

    @classmethod
    def parse(cls, content: bytes, places: frozenset[str], source: str = "dou") -> list[Vacancy]:
        feed = feedparser.parse(content)  # bytes, чтобы учесть encoding из XML
        if feed.get("bozo"):
            log.warning("RSS разобран с предупреждением: %s", feed.get("bozo_exception"))
        return [cls._parse_entry(entry, places, source) for entry in feed.entries]

    @classmethod
    def _parse_entry(cls, entry, places: frozenset[str], source: str) -> Vacancy:
        link = entry.link.split("?")[0]  # убираем utm_source
        match = _VACANCY_ID_RE.search(link)
        title, company, locations = cls.split_title(entry.title, places)

        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        return Vacancy(
            source=source,
            id=match.group(1) if match else link,
            title=title,
            url=link,
            company=company,
            locations=tuple(locations),
            published=published,
            text=BeautifulSoup(entry.get("summary", ""), "lxml").get_text(" ", strip=True),
        )


class DouFiltersParser:
    """Достаёт значения фильтров из HTML страницы со списком вакансий."""

    LIST_KEYS = ("category", "city", "exp")   # фильтры со списком значений
    FLAGS = ("remote", "relocation")          # фильтры-флаги без значения
    EXP_ORDER = ["0-1", "1-3", "3-5", "5plus"]

    @classmethod
    def parse(cls, html: str) -> FilterOptions:
        soup = BeautifulSoup(html, "lxml")
        page = cls._collect(soup)

        # Форма, где лежит список категорий: там значения «чище», чем по всей странице.
        category_select = soup.find("select", attrs={"name": "category"})
        form = category_select.find_parent("form") if category_select else None
        scoped = cls._collect(form) if form else {k: [] for k in cls.LIST_KEYS}

        # Опыт в форме неполный, поэтому объединяем форму и всю страницу.
        experiences = list(dict.fromkeys(scoped["exp"] + page["exp"]))
        experiences.sort(
            key=lambda v: cls.EXP_ORDER.index(v) if v in cls.EXP_ORDER else len(cls.EXP_ORDER)
        )

        return FilterOptions(
            categories=scoped["category"] or page["category"],
            cities=scoped["city"] or page["city"],
            experiences=experiences,
            flags=list(cls.FLAGS),
        )

    @classmethod
    def _collect(cls, scope) -> dict[str, list[str]]:
        """Значения фильтров из <select>, <input> и ссылок внутри scope."""
        values: dict[str, list[str]] = {k: [] for k in cls.LIST_KEYS}

        def add(key: str | None, value: str | None) -> None:
            if key in values and value and value not in values[key]:
                values[key].append(value)

        for select in scope.find_all("select"):
            for option in select.find_all("option"):
                add(select.get("name"), option.get("value"))

        for field in scope.find_all("input"):
            add(field.get("name"), field.get("value"))

        for link in scope.find_all("a", href=True):
            query = parse_qs(urlparse(link["href"]).query, keep_blank_values=True)
            for key, vals in query.items():
                for value in vals:
                    add(key, value)

        return values


@register_source
class DouSource(JobSource):
    name = "dou"

    _EXPERIENCE = {
        Experience.UP_TO_1: "0-1",
        Experience.Y1_3: "1-3",
        Experience.Y3_5: "3-5",
        Experience.Y5_PLUS: "5plus",
    }

    def build_params(self, query: SearchQuery) -> dict[str, str]:
        """SearchQuery -> параметры RSS-ленты DOU."""
        self._require_unset(query, "english", "region", "min_salary")

        params: dict[str, str] = {}
        if query.category:
            params["category"] = query.category
        if query.experience is not None:
            try:
                params["exp"] = self._EXPERIENCE[query.experience]
            except KeyError:
                raise UnsupportedQuery(f"DOU: опыт {query.experience.value!r} не поддерживается лентой")
        if query.city:
            params["city"] = query.city
        if query.employment is not None:
            if query.employment is not Employment.REMOTE:
                raise UnsupportedQuery("DOU: из форматов работы поддерживается только удалёнка")
            params["remote"] = ""        # в URL получится ?remote= (проверено: работает)
        if query.relocation:
            params["relocation"] = ""    # в ленте не проверялось
        return params

    async def fetch(self, query: SearchQuery | None = None) -> list[Vacancy]:
        params = self.build_params(query or SearchQuery())
        places = await self._places()
        response = await self._get(FEED_URL, params=params)
        return DouFeedParser.parse(response.content, places, source=self.name)

    async def fetch_filter_options(self) -> FilterOptions:
        response = await self._get(LISTING_URL)
        return DouFiltersParser.parse(response.text)

    async def validate_query(self, query: SearchQuery) -> None:
        self.build_params(query)

    async def _places(self) -> frozenset[str]:
        options = await self.get_filter_options()
        return frozenset(options.cities) | LOCATION_MARKERS