
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from ..models import Experience, FilterOptions, SearchQuery, Vacancy
from ..utils import casefold_key, normalize
from .base import JobSource, UnsupportedQuery, register_source


log = logging.getLogger(__name__)

BASE_URL = "https://djinni.co"
JOBS_URL = f"{BASE_URL}/jobs/"
RSS_URL = f"{BASE_URL}/jobs/rss/"

_JOB_ID_RE = re.compile(r"/jobs/(\d+)-")


class DjinniFeedParser:
    """Разбор RSS-ленты Djinni (до 100 вакансий, новые сверху)."""

    @classmethod
    def parse(cls, content: bytes, source: str = "djinni") -> list[Vacancy]:
        feed = feedparser.parse(content)
        if feed.get("bozo"):
            log.warning("RSS разобран с предупреждением: %s", feed.get("bozo_exception"))
        parsed = (cls._parse_entry(entry, source) for entry in feed.entries)
        return [v for v in parsed if v is not None]

    @staticmethod
    def parse_categories(content: bytes) -> list[str]:
        """Список категорий (значения primary_keyword) из шапки ленты."""
        feed = feedparser.parse(content)
        terms = [tag.get("term") for tag in feed.feed.get("tags", [])]
        return list(dict.fromkeys(t for t in terms if t))

    @staticmethod
    def _parse_entry(entry, source: str) -> Vacancy | None:
        link = entry.get("link", "").split("?")[0]
        match = _JOB_ID_RE.search(link)
        if not match:
            log.warning("Djinni: не удалось получить id вакансии из %r", link)
            return None

        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        # У вакансии одна непустая категория (вторая <category> пустая).
        category = next((t.get("term") for t in entry.get("tags", []) if t.get("term")), None)

        return Vacancy(
            source=source,
            id=match.group(1),
            title=normalize(entry.get("title", "")),
            url=link,
            category=category,
            published=published,
            text=BeautifulSoup(entry.get("summary", ""), "lxml").get_text(" ", strip=True),
        )


class DjinniListingParser:

    @classmethod
    def parse(cls, html: str, source: str = "djinni") -> list[Vacancy]:
        soup = BeautifulSoup(html, "lxml")
        parsed = (cls._parse_card(card, source) for card in soup.select("div.job-item"))
        return [v for v in parsed if v is not None]

    @staticmethod
    def _parse_card(card, source: str) -> Vacancy | None:
        id_match = re.search(r"job-item-(\d+)", card.get("id", ""))
        link = card.select_one("a.job_item__header-link[href]")
        title_el = card.select_one("h2.job-item__position")
        if not (id_match and link and title_el):
            return None
        vacancy_id = id_match.group(1)

        # Компания лежит рядом с заголовком, в том же блоке <div class="col">.
        company_el = title_el.parent.select_one("span.small") if title_el.parent else None
        company = normalize(company_el.get_text(" ", strip=True)) if company_el else None

        # Значки «$»…«$$$$»: это уровень зарплаты относительно рынка, а не сумма.
        tier_el = card.select_one("header div.fs-5 span")
        tier = normalize(tier_el.get_text()) if tier_el else ""

        # Строка меты: «формат · город · опыт · английский · домен».
        # Состав меняется (например, нет опыта), поэтому город определяем по классу,
        # а остальное складываем в tags как есть (текст на языке интерфейса сайта).
        meta = next(
            (d for d in card.select("div.fw-medium") if d.find("span", class_="middot", recursive=False)),
            None,
        )
        locations: list[str] = []
        tags: list[str] = []
        if meta is not None:
            for span in meta.find_all("span", recursive=False):
                if "middot" in span.get("class", []):
                    continue
                text = normalize(span.get_text(" ", strip=True))
                if not text:
                    continue
                (locations if span.select_one(".location-text") else tags).append(text)
        if re.fullmatch(r"\$+", tier):
            tags.append(tier)

        snippet = card.select_one(f"#job-description-{vacancy_id} .js-truncated-text")

        return Vacancy(
            source=source,
            id=vacancy_id,
            title=normalize(title_el.get_text(" ", strip=True)),
            url=urljoin(BASE_URL, link["href"]).split("?")[0],
            company=company,
            locations=tuple(locations),
            tags=tuple(tags),
            text=normalize(snippet.get_text(" ", strip=True)) if snippet else "",
        )


class DjinniFiltersParser:

    GROUPS = ("exp_level", "employment", "english_level", "region", "location", "country")

    @classmethod
    def parse_form(cls, html: str) -> dict[str, list[dict]]:

        soup = BeautifulSoup(html, "lxml")

        def label_of(el):
            if el.get("id"):
                label = soup.find("label", attrs={"for": el["id"]})
                if label:
                    return normalize(label.get_text(" ", strip=True))
            parent = el.find_parent("label")
            return normalize(parent.get_text(" ", strip=True)) if parent else None

        groups: dict[str, list[dict]] = {name: [] for name in cls.GROUPS}
        for el in soup.find_all(["input", "option"]):
            if el.name == "option":
                select = el.find_parent("select")
                name = select.get("name") if select else None
                label = normalize(el.get_text(" ", strip=True))
            else:
                name = el.get("name")
                label = label_of(el)

            value = el.get("value")
            if name in groups and value:
                item = {"value": value, "label": label}
                if item not in groups[name]:
                    groups[name].append(item)
        return groups


@register_source
class DjinniSource(JobSource):
    name = "djinni"

    MIN_CATEGORIES = 100   # меньше считаем сбоем: в шапке ленты их около 170
    MAX_SALARY = 10_000    # предел ползунка зарплаты на сайте, $


    _EXPERIENCE = {
        Experience.NONE: ["no_exp"],
        Experience.UP_TO_1: ["no_exp", "1y"],
        Experience.Y1_3: ["1y", "2y", "3y"],
        Experience.Y3_5: ["3y", "4y", "5y"],
        Experience.Y5_PLUS: [f"{years}y" for years in range(5, 11)],
    }

    def build_params(self, query: SearchQuery, options: FilterOptions) -> dict[str, str | list[str]]:
        self._require_unset(query, "relocation")

        params: dict[str, str | list[str]] = {}
        if query.category:
            params["primary_keyword"] = query.category
        if query.experience is not None:
            params["exp_level"] = list(self._EXPERIENCE[query.experience])
        if query.city:
            params["location"] = self._resolve_city(query.city, options)
        if query.employment is not None:
            params["employment"] = query.employment.value
        if query.english:
            params["english_level"] = query.english
        if query.region is not None:
            params["region"] = query.region.value
        if query.min_salary:  # 0 = «без ограничения», как на сайте по умолчанию
            if not 0 < query.min_salary <= self.MAX_SALARY:
                raise ValueError(f"min_salary должен быть от 1 до {self.MAX_SALARY}, получено {query.min_salary}")
            params["salary"] = str(query.min_salary)
        return params

    @staticmethod
    def _resolve_city(city: str, options: FilterOptions) -> str:

        wanted = casefold_key(city)
        for item in options.groups.get("location", []):
            if wanted in (casefold_key(item["value"]), casefold_key(item.get("label") or "")):
                return item["value"]
        raise UnsupportedQuery(f"Djinni: города {city!r} нет среди фильтров сайта")

    async def _params_for(self, query: SearchQuery | None) -> dict:
        query = query or SearchQuery()
        # Фильтры нужны только для перевода города, поэтому лишний раз их не качаем.
        options = await self.get_filter_options() if query.city else FilterOptions()
        return self.build_params(query, options)

    async def fetch(self, query: SearchQuery | None = None) -> list[Vacancy]:

        params = await self._params_for(query)
        response = await self._get(RSS_URL, params=params)
        return DjinniFeedParser.parse(response.content, source=self.name)

    async def fetch_listing(self, query: SearchQuery | None = None, page: int = 1) -> list[Vacancy]:

        params = {"search_type": "basic-search", **await self._params_for(query)}
        if page > 1:
            params["page"] = str(page)
        response = await self._get(JOBS_URL, params=params)
        if page > 1 and response.url.params.get("page") != str(page):
            return []  # страницы за последней сайт молча перенаправляет на первую
        return DjinniListingParser.parse(response.text, source=self.name)

    async def fetch_filter_options(self) -> FilterOptions:
        html = (await self._get(JOBS_URL)).text
        groups = DjinniFiltersParser.parse_form(html)
        return FilterOptions(
            categories=await self._fetch_categories(),
            cities=[item["label"] for item in groups["location"] if item.get("label")],
            experiences=[item["value"] for item in groups["exp_level"]],
            groups=groups,
        )
        
    async def validate_query(self, query: SearchQuery) -> None:
        await self._params_for(query)

    async def _fetch_categories(self) -> list[str]:

        for params in ({"primary_keyword": "Python", "exp_level": "2y"}, None):
            response = await self._get(RSS_URL, params=params)
            categories = DjinniFeedParser.parse_categories(response.content)
            if len(categories) >= self.MIN_CATEGORIES:
                return categories
        raise RuntimeError("Djinni: не удалось получить список категорий из RSS")
