from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

REGISTRY_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "missing_editorial.json"
)

RUSSIAN_NAMES_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "russian_names.json"
)

POKEAPI_DIR = (
    BASE_DIR
    / "data"
    / "source"
    / "pokeapi"
)

OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "editorial_source_dataset.json"
)


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


def build_names_index(
    payload: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    entries = payload.get("entries")

    if not isinstance(entries, list):
        raise ValueError(
            "В russian_names.json отсутствует список entries"
        )

    result: dict[int, dict[str, Any]] = {}

    for entry in entries:
        pokeapi_id = int(entry["pokeapi_id"])

        if pokeapi_id in result:
            raise ValueError(
                f"Дубликат русского имени: #{pokeapi_id}"
            )

        result[pokeapi_id] = entry

    return result


def select_description_source(
    flavor_texts: list[dict[str, Any]],
) -> dict[str, str] | None:
    if not flavor_texts:
        return None

    preferred_versions = [
        "scarlet",
        "violet",
        "legends-arceus",
        "sword",
        "shield",
        "ultra-sun",
        "ultra-moon",
        "sun",
        "moon",
        "omega-ruby",
        "alpha-sapphire",
        "x",
        "y",
        "black-2",
        "white-2",
        "black",
        "white",
        "platinum",
        "diamond",
        "pearl",
        "emerald",
        "firered",
        "leafgreen",
        "crystal",
        "gold",
        "silver",
        "yellow",
        "red",
        "blue",
    ]

    by_version: dict[str, dict[str, str]] = {}

    for item in flavor_texts:
        text = item.get("text")
        version = item.get("version")

        if not isinstance(text, str):
            continue

        if not isinstance(version, str):
            continue

        if not text.strip():
            continue

        by_version[version] = {
            "text": text.strip(),
            "version": version,
        }

    for version in preferred_versions:
        selected = by_version.get(version)

        if selected is not None:
            return selected

    first = flavor_texts[0]
    text = first.get("text")
    version = first.get("version", "")

    if not isinstance(text, str) or not text.strip():
        return None

    return {
        "text": text.strip(),
        "version": str(version),
    }


def select_fact_source(
    flavor_texts: list[dict[str, Any]],
    description_source: dict[str, str] | None,
) -> dict[str, str] | None:
    description_text = (
        description_source["text"]
        if description_source is not None
        else None
    )

    candidates: list[dict[str, str]] = []

    seen_texts: set[str] = set()

    for item in flavor_texts:
        text = item.get("text")
        version = item.get("version")

        if not isinstance(text, str):
            continue

        cleaned = text.strip()

        if not cleaned:
            continue

        if cleaned == description_text:
            continue

        if cleaned in seen_texts:
            continue

        seen_texts.add(cleaned)

        candidates.append(
            {
                "text": cleaned,
                "version": (
                    str(version)
                    if version is not None
                    else ""
                ),
            }
        )

    if not candidates:
        return description_source

    candidates.sort(
        key=lambda item: len(item["text"]),
        reverse=True,
    )

    return candidates[0]


def load_pokeapi_record(
    pokeapi_id: int,
    slug: str,
) -> dict[str, Any]:
    path = (
        POKEAPI_DIR
        / f"{pokeapi_id:04d}_{slug}.json"
    )

    return load_json(path)


def build_dataset() -> list[dict[str, Any]]:
    registry_payload = load_json(REGISTRY_PATH)
    names_payload = load_json(RUSSIAN_NAMES_PATH)

    registry_entries = registry_payload.get("entries")

    if not isinstance(registry_entries, list):
        raise ValueError(
            "В missing_editorial.json отсутствует список entries"
        )

    names_index = build_names_index(names_payload)

    result: list[dict[str, Any]] = []

    for registry_entry in registry_entries:
        pokeapi_id = int(
            registry_entry["pokeapi_id"]
        )

        slug = str(
            registry_entry["slug"]
        )

        russian_name = names_index.get(
            pokeapi_id
        )

        if russian_name is None:
            raise ValueError(
                f"Не найдено русское имя: #{pokeapi_id} {slug}"
            )

        pokeapi_record = load_pokeapi_record(
            pokeapi_id,
            slug,
        )

        flavor_texts = pokeapi_record.get(
            "flavor_texts_en",
            [],
        )

        if not isinstance(flavor_texts, list):
            flavor_texts = []

        description_source = (
            select_description_source(
                flavor_texts
            )
        )

        fact_source = select_fact_source(
            flavor_texts,
            description_source,
        )

        result.append(
            {
                "pokeapi_id": pokeapi_id,
                "slug": slug,
                "name_en": pokeapi_record.get(
                    "name_en"
                ),
                "name_ru": russian_name["name_ru"],
                "genera_en": pokeapi_record.get(
                    "genera_en",
                    [],
                ),
                "types": pokeapi_record.get(
                    "types",
                    [],
                ),
                "abilities": pokeapi_record.get(
                    "abilities",
                    [],
                ),
                "height_dm": pokeapi_record.get(
                    "height_dm"
                ),
                "weight_hg": pokeapi_record.get(
                    "weight_hg"
                ),
                "generation": pokeapi_record.get(
                    "generation"
                ),
                "is_baby": pokeapi_record.get(
                    "is_baby",
                    False,
                ),
                "is_legendary": pokeapi_record.get(
                    "is_legendary",
                    False,
                ),
                "is_mythical": pokeapi_record.get(
                    "is_mythical",
                    False,
                ),
                "description_source_en": (
                    description_source
                ),
                "fact_source_en": fact_source,
                "all_flavor_texts_en": flavor_texts,
                "source_url": (
                    pokeapi_record
                    .get("sources", {})
                    .get("species")
                ),
                "status": "source_ready",
            }
        )

    return result


def validate_dataset(
    entries: list[dict[str, Any]],
) -> None:
    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()

    missing_descriptions: list[str] = []
    missing_facts: list[str] = []
    missing_names: list[str] = []

    for entry in entries:
        pokeapi_id = int(entry["pokeapi_id"])
        slug = str(entry["slug"])

        if pokeapi_id in seen_ids:
            raise ValueError(
                f"Дубликат ID: {pokeapi_id}"
            )

        if slug in seen_slugs:
            raise ValueError(
                f"Дубликат slug: {slug}"
            )

        seen_ids.add(pokeapi_id)
        seen_slugs.add(slug)

        if not entry.get("name_ru"):
            missing_names.append(slug)

        if not entry.get("description_source_en"):
            missing_descriptions.append(slug)

        if not entry.get("fact_source_en"):
            missing_facts.append(slug)

    if missing_names:
        raise ValueError(
            "Нет русских имён: "
            + ", ".join(missing_names[:20])
        )

    if missing_descriptions:
        raise ValueError(
            "Нет исходных описаний: "
            + ", ".join(
                missing_descriptions[:20]
            )
        )

    if missing_facts:
        raise ValueError(
            "Нет исходных фактов: "
            + ", ".join(
                missing_facts[:20]
            )
        )


def save_dataset(
    entries: list[dict[str, Any]],
) -> None:
    payload = {
        "schema_version": 1,
        "language": "ru",
        "total": len(entries),
        "status": "source_ready",
        "entries": entries,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    entries = build_dataset()
    validate_dataset(entries)
    save_dataset(entries)

    print("Промежуточный датасет собран")
    print(f"Всего записей: {len(entries)}")
    print(f"Файл: {OUTPUT_PATH}")

    print()
    print("Первые записи:")

    for entry in entries[:5]:
        description = entry[
            "description_source_en"
        ]

        fact = entry["fact_source_en"]

        print(
            f"#{entry['pokeapi_id']:04d} "
            f"{entry['slug']} → "
            f"{entry['name_ru']}"
        )

        print(
            f"  Описание: "
            f"{description['version']}"
        )

        print(
            f"  Факт: "
            f"{fact['version']}"
        )


if __name__ == "__main__":
    main()