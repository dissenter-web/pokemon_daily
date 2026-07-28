from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_PATH = BASE_DIR / "data" / "source" / "pokemon_species.csv"
OUTPUT_PATH = BASE_DIR / "data" / "source" / "missing_editorial.json"


def load_species(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Исходный CSV не найден: {path}")

    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    required_columns = {
        "pokeapi_id",
        "slug",
        "name_en",
        "name_ru",
        "content_ready",
    }

    actual_columns = set(rows[0]) if rows else set()
    missing_columns = required_columns - actual_columns

    if missing_columns:
        columns = ", ".join(sorted(missing_columns))
        raise ValueError(f"В CSV отсутствуют столбцы: {columns}")

    return rows


def build_missing_registry(
    species_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []

    for row in species_rows:
        if row["content_ready"].strip().lower() != "f":
            continue

        registry.append(
            {
                "pokeapi_id": int(row["pokeapi_id"]),
                "slug": row["slug"].strip(),
                "name_en": row["name_en"].strip(),
                "name_ru": row["name_ru"].strip() or None,
                "source_url": (
                    "https://pokeapi.co/api/v2/pokemon-species/"
                    f"{row['pokeapi_id']}/"
                ),
                "status": "missing",
            }
        )

    return registry


def save_registry(
    registry: list[dict[str, Any]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "total": len(registry),
        "entries": registry,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    species_rows = load_species(SOURCE_PATH)
    registry = build_missing_registry(species_rows)
    save_registry(registry, OUTPUT_PATH)

    print(f"Записей в CSV: {len(species_rows)}")
    print(f"Недостающих карточек: {len(registry)}")
    print(f"Реестр создан: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()