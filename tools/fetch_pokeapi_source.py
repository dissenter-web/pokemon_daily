from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent.parent

REGISTRY_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "missing_editorial.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "source"
    / "pokeapi"
)

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.15
MAX_RETRIES = 3

USER_AGENT = "PokemonDailyEditorialDataset/1.0"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Ожидался JSON-объект: {path}")

    return data


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                payload = response.read().decode("utf-8")
                data = json.loads(payload)

            if not isinstance(data, dict):
                raise ValueError(
                    f"API вернуло неожиданный формат: {url}"
                )

            return data

        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as error:
            last_error = error

            print(
                f"  Ошибка запроса, попытка "
                f"{attempt}/{MAX_RETRIES}: {error}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(
        f"Не удалось загрузить {url}: {last_error}"
    )


def clean_text(value: str) -> str:
    return " ".join(
        value
        .replace("\n", " ")
        .replace("\f", " ")
        .replace("\r", " ")
        .split()
    )


def extract_english_names(
    species_data: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}

    for item in species_data.get("names", []):
        language = item.get("language", {}).get("name")

        if language != "en":
            continue

        name = item.get("name")

        if isinstance(name, str) and name.strip():
            result["name_en"] = name.strip()
            break

    return result


def extract_english_genera(
    species_data: dict[str, Any],
) -> list[str]:
    genera: list[str] = []

    for item in species_data.get("genera", []):
        language = item.get("language", {}).get("name")

        if language != "en":
            continue

        genus = item.get("genus")

        if not isinstance(genus, str):
            continue

        cleaned = clean_text(genus)

        if cleaned and cleaned not in genera:
            genera.append(cleaned)

    return genera


def extract_english_flavor_texts(
    species_data: dict[str, Any],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen_texts: set[str] = set()

    for item in species_data.get(
        "flavor_text_entries",
        [],
    ):
        language = item.get("language", {}).get("name")

        if language != "en":
            continue

        raw_text = item.get("flavor_text")

        if not isinstance(raw_text, str):
            continue

        text = clean_text(raw_text)

        if not text or text in seen_texts:
            continue

        version = item.get("version", {}).get("name", "")

        result.append(
            {
                "text": text,
                "version": version,
            }
        )

        seen_texts.add(text)

    return result


def extract_names(
    items: list[dict[str, Any]],
    key: str,
) -> list[str]:
    result: list[str] = []

    for item in items:
        value = item.get(key, {}).get("name")

        if isinstance(value, str) and value:
            result.append(value)

    return result


def build_source_record(
    registry_entry: dict[str, Any],
    species_data: dict[str, Any],
    pokemon_data: dict[str, Any],
) -> dict[str, Any]:
    pokeapi_id = int(registry_entry["pokeapi_id"])
    slug = str(registry_entry["slug"])

    english_names = extract_english_names(species_data)

    abilities = extract_names(
        pokemon_data.get("abilities", []),
        "ability",
    )

    types = extract_names(
        pokemon_data.get("types", []),
        "type",
    )

    generation = (
        species_data
        .get("generation", {})
        .get("name")
    )

    evolution_chain_url = (
        species_data
        .get("evolution_chain", {})
        .get("url")
    )

    return {
        "schema_version": 1,
        "pokeapi_id": pokeapi_id,
        "slug": slug,
        "name_en": english_names.get(
            "name_en",
            registry_entry.get("name_en"),
        ),
        "genera_en": extract_english_genera(
            species_data
        ),
        "flavor_texts_en": (
            extract_english_flavor_texts(
                species_data
            )
        ),
        "types": types,
        "abilities": abilities,
        "height_dm": pokemon_data.get("height"),
        "weight_hg": pokemon_data.get("weight"),
        "generation": generation,
        "is_baby": bool(
            species_data.get("is_baby", False)
        ),
        "is_legendary": bool(
            species_data.get(
                "is_legendary",
                False,
            )
        ),
        "is_mythical": bool(
            species_data.get(
                "is_mythical",
                False,
            )
        ),
        "evolution_chain_url": evolution_chain_url,
        "sources": {
            "species": (
                "https://pokeapi.co/api/v2/"
                f"pokemon-species/{pokeapi_id}/"
            ),
            "pokemon": (
                "https://pokeapi.co/api/v2/"
                f"pokemon/{pokeapi_id}/"
            ),
        },
    }


def save_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    registry = load_json(REGISTRY_PATH)
    entries = registry.get("entries")

    if not isinstance(entries, list):
        raise ValueError(
            "В реестре отсутствует список entries"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    total = len(entries)
    downloaded = 0
    skipped = 0
    failed: list[dict[str, Any]] = []

    for index, entry in enumerate(
        entries,
        start=1,
    ):
        pokeapi_id = int(entry["pokeapi_id"])
        slug = str(entry["slug"])

        output_path = (
            OUTPUT_DIR
            / f"{pokeapi_id:04d}_{slug}.json"
        )

        if output_path.exists():
            skipped += 1

            print(
                f"[{index}/{total}] "
                f"{slug}: уже загружен"
            )

            continue

        species_url = (
            "https://pokeapi.co/api/v2/"
            f"pokemon-species/{pokeapi_id}/"
        )

        pokemon_url = (
            "https://pokeapi.co/api/v2/"
            f"pokemon/{pokeapi_id}/"
        )

        print(
            f"[{index}/{total}] "
            f"Загрузка {slug}..."
        )

        try:
            species_data = fetch_json(
                species_url
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

            pokemon_data = fetch_json(
                pokemon_url
            )

            source_record = build_source_record(
                registry_entry=entry,
                species_data=species_data,
                pokemon_data=pokemon_data,
            )

            save_json(
                output_path,
                source_record,
            )

            downloaded += 1

        except Exception as error:
            print(
                f"  Не удалось обработать "
                f"{slug}: {error}"
            )

            failed.append(
                {
                    "pokeapi_id": pokeapi_id,
                    "slug": slug,
                    "error": str(error),
                }
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    failures_path = (
        BASE_DIR
        / "data"
        / "source"
        / "pokeapi_failures.json"
    )

    save_json(
        failures_path,
        {
            "schema_version": 1,
            "failed": failed,
        },
    )

    print()
    print("Сбор данных завершён")
    print(f"Всего в реестре: {total}")
    print(f"Загружено сейчас: {downloaded}")
    print(f"Уже существовало: {skipped}")
    print(f"Ошибок: {len(failed)}")
    print(f"Каталог: {OUTPUT_DIR}")

    if failed:
        print(
            f"Список ошибок: {failures_path}"
        )


if __name__ == "__main__":
    main()