
import asyncio
import logging

from src.jobs_parsing.models import Employment, Experience, SearchQuery
from src.jobs_parsing.sources import DjinniSource, UnsupportedQuery, available_sources, create_source

QUERY = SearchQuery(category="Python", experience=Experience.Y1_3, employment=Employment.REMOTE)


async def demo(name: str) -> None:
    print(f"\n=== {name} ===")
    async with create_source(name) as src:
        options = await src.get_filter_options()  # первый раз скачает и сохранит в cache/
        print(f"категорий: {len(options.categories)}, городов: {len(options.cities)}, "
              f"опыт: {options.experiences}")

        try:
            vacancies = await src.fetch(QUERY)
        except UnsupportedQuery as e:
            print("Не поддерживается:", e)
            return
        print(f"{QUERY}\n -> {len(vacancies)} вакансий")
        for v in vacancies[:3]:
            print(" ", v.uid, "|", v.title, "|", v.company, "|", v.category, "|", v.locations, "|", v.published)

        if isinstance(src, DjinniSource):  # HTML-список: с компанией и метками карточки
            rich = await src.fetch_listing(QUERY)
            print(f"HTML-список: {len(rich)} вакансий")
            for v in rich[:3]:
                print(" ", v.uid, "|", v.title, "|", v.company, "|", v.locations, "|", v.tags)


async def main() -> None:
    for name in available_sources():
        await demo(name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
