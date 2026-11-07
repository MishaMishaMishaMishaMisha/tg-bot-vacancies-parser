from src.services import format_vacancy
from src.services.jobs import Vacancy


def test_format_escapes_html_and_contains_link_and_source():
    vacancy = Vacancy(
        source="djinni",
        id="1",
        title="C# <Dev> & Co",
        url="https://example.com/?a=1&b=2",
        company="A&B",
        locations=("Київ", "віддалено"),
        salary="$$$",
        tags=("2 роки досвіду",),
    )

    message = format_vacancy(vacancy)

    assert "<b>C# &lt;Dev&gt; &amp; Co</b>" in message
    assert "A&amp;B · Київ, віддалено" in message
    assert 'href="https://example.com/?a=1&amp;b=2"' in message
    assert message.endswith("· Djinni")


def test_format_shortens_long_description():
    vacancy = Vacancy(source="dou", id="1", title="T", url="https://example.com/1", text="слово " * 200)

    message = format_vacancy(vacancy)

    assert message.count("…") == 1
    assert len(message) < 700


def test_format_skips_missing_parts():
    vacancy = Vacancy(source="dou", id="1", title="Only title", url="https://example.com/1")

    lines = format_vacancy(vacancy).splitlines()

    assert lines[0] == "<b>Only title</b>"
    assert len(lines) == 3   # заголовок, пустая строка и ссылка: без пустых «компании» и меток
    assert "None" not in "\n".join(lines)
