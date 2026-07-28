from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent

REGISTRY_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "missing_editorial.json"
)

OUTPUT_JSON_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "russian_names.json"
)

OUTPUT_CSV_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "russian_names.csv"
)

SOURCE_URL = (
    "https://bulbapedia.bulbagarden.net/wiki/"
    "List_of_Russian_Pok%C3%A9mon_names"
)

USER_AGENT = "PokemonDailyEditorialDataset/1.0"

POKEDEX_NUMBER_PATTERN = re.compile(r"#?0*(\d{1,4})$")
CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            f"Ожидался JSON-объект: {path}"
        )

    return payload


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
        },
    )

    with urlopen(request, timeout=60) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        )


def normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def parse_pokedex_number(value: str) -> int | None:
    cleaned = normalize_text(value)
    match = POKEDEX_NUMBER_PATTERN.fullmatch(cleaned)

    if match is None:
        return None

    return int(match.group(1))


def find_russian_name(
    values: list[str],
    english_name: str,
) -> str | None:
    try:
        english_index = values.index(english_name)
    except ValueError:
        english_index = -1

    candidates = (
        values[english_index + 1:]
        if english_index >= 0
        else values
    )

    for value in candidates:
        if CYRILLIC_PATTERN.search(value):
            return value

    return None


def parse_names(html: str) -> dict[int, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[int, dict[str, Any]] = {}

    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])

        if len(cells) < 3:
            continue

        values = [
            normalize_text(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )
            for cell in cells
        ]

        pokedex_id = parse_pokedex_number(
            values[0]
        )

        if pokedex_id is None:
            continue

        english_name: str | None = None

        for value in values[1:]:
            if not value:
                continue

            if CYRILLIC_PATTERN.search(value):
                continue

            if value.isdigit():
                continue

            english_name = value
            break

        if english_name is None:
            continue

        russian_name = find_russian_name(
            values,
            english_name,
        )

        if russian_name is None:
            continue

        result[pokedex_id] = {
            "pokeapi_id": pokedex_id,
            "name_en": english_name,
            "name_ru": russian_name,
        }

    return result


def load_required_entries(
    registry_path: Path,
) -> list[dict[str, Any]]:
    registry = load_json(registry_path)
    entries = registry.get("entries")

    if not isinstance(entries, list):
        raise ValueError(
            "В реестре отсутствует список entries"
        )

    return entries


def build_required_names(
    source_names: dict[int, dict[str, Any]],
    registry_entries: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for entry in registry_entries:
        pokeapi_id = int(entry["pokeapi_id"])
        slug = str(entry["slug"])
        expected_name_en = str(entry["name_en"])

        source_entry = source_names.get(
            pokeapi_id
        )

        if source_entry is None:
            missing.append(
                {
                    "pokeapi_id": pokeapi_id,
                    "slug": slug,
                    "name_en": expected_name_en,
                    "reason": (
                        "Имя отсутствует "
                        "в источнике"
                    ),
                }
            )
            continue

        matched.append(
            {
                "pokeapi_id": pokeapi_id,
                "slug": slug,
                "name_en": expected_name_en,
                "name_ru": (
                    source_entry["name_ru"]
                ),
                "source_name_en": (
                    source_entry["name_en"]
                ),
            }
        )

    return matched, missing


def save_json(
    path: Path,
    matched: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    payload = {
        "schema_version": 1,
        "language": "ru",
        "source_url": SOURCE_URL,
        "total": len(matched),
        "missing_total": len(missing),
        "entries": matched,
        "missing": missing,
    }

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def save_csv(
    path: Path,
    entries: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "pokeapi_id",
        "slug",
        "name_en",
        "name_ru",
        "source_name_en",
    ]

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(entries)


def main() -> None:
    print("Загрузка страницы с русскими именами...")

    html = fetch_html(SOURCE_URL)
    source_names = parse_names(html)

    print(
        "Найдено имён в источнике: "
        f"{len(source_names)}"
    )

    registry_entries = load_required_entries(
        REGISTRY_PATH
    )

    matched, missing = build_required_names(
        source_names=source_names,
        registry_entries=registry_entries,
    )

    save_json(
        OUTPUT_JSON_PATH,
        matched,
        missing,
    )

    save_csv(
        OUTPUT_CSV_PATH,
        matched,
    )

    print()
    print("Обработка завершена")
    print(
        f"Требуется имён: "
        f"{len(registry_entries)}"
    )
    print(f"Сопоставлено: {len(matched)}")
    print(f"Не найдено: {len(missing)}")
    print(f"JSON: {OUTPUT_JSON_PATH}")
    print(f"CSV: {OUTPUT_CSV_PATH}")

    if missing:
        print()
        print("Первые отсутствующие записи:")

        for entry in missing[:20]:
            print(
                f"  #{entry['pokeapi_id']:04d} "
                f"{entry['slug']} "
                f"({entry['name_en']})"
            )


if __name__ == "__main__":
    main()