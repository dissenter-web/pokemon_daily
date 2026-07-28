from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_PATH = (
    BASE_DIR
    / "data"
    / "source"
    / "editorial_source_dataset.json"
)

BATCHES_DIR = (
    BASE_DIR
    / "data"
    / "editorial_batches"
)

BATCH_SIZE = 25


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Исходный файл не найден: {path}"
        )

    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            f"Ожидался JSON-объект: {path}"
        )

    return payload


def clean_source_text(value: str) -> str:
    return (
        value
        .replace("\u00ad", "")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\f", " ")
        .strip()
    )


def build_batch_entry(
    entry: dict[str, Any],
) -> dict[str, Any]:
    description_source = entry.get(
        "description_source_en"
    )

    fact_source = entry.get(
        "fact_source_en"
    )

    if not isinstance(description_source, dict):
        raise ValueError(
            f"Нет источника описания: {entry.get('slug')}"
        )

    if not isinstance(fact_source, dict):
        raise ValueError(
            f"Нет источника факта: {entry.get('slug')}"
        )

    description_text = description_source.get("text")
    fact_text = fact_source.get("text")

    if not isinstance(description_text, str):
        raise ValueError(
            f"Некорректное описание: {entry.get('slug')}"
        )

    if not isinstance(fact_text, str):
        raise ValueError(
            f"Некорректный факт: {entry.get('slug')}"
        )

    return {
        "pokeapi_id": int(entry["pokeapi_id"]),
        "slug": str(entry["slug"]),
        "name_en": str(entry["name_en"]),
        "name_ru": str(entry["name_ru"]),
        "description_source_en": clean_source_text(
            description_text
        ),
        "fact_source_en": clean_source_text(
            fact_text
        ),
        "description_ru": "",
        "fact_ru": "",
        "source_url": entry["source_url"],
        "status": "translation_pending",
    }


def split_batches(
    entries: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    return [
        entries[index:index + BATCH_SIZE]
        for index in range(
            0,
            len(entries),
            BATCH_SIZE,
        )
    ]


def save_batch(
    batch_number: int,
    entries: list[dict[str, Any]],
) -> Path:
    first_id = entries[0]["pokeapi_id"]
    last_id = entries[-1]["pokeapi_id"]

    filename = (
        f"batch_{batch_number:02d}_"
        f"{first_id:04d}_{last_id:04d}.json"
    )

    path = BATCHES_DIR / filename

    payload = {
        "schema_version": 1,
        "language": "ru",
        "batch_number": batch_number,
        "total": len(entries),
        "status": "translation_pending",
        "entries": entries,
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

    return path


def main() -> None:
    source = load_json(SOURCE_PATH)
    source_entries = source.get("entries")

    if not isinstance(source_entries, list):
        raise ValueError(
            "В исходном датасете отсутствует список entries"
        )

    prepared_entries = [
        build_batch_entry(entry)
        for entry in source_entries
    ]

    batches = split_batches(prepared_entries)

    if BATCHES_DIR.exists():
        shutil.rmtree(BATCHES_DIR)

    BATCHES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Создание рабочих пакетов")
    print(f"Всего записей: {len(prepared_entries)}")
    print(f"Размер пакета: {BATCH_SIZE}")
    print(f"Количество пакетов: {len(batches)}")
    print()

    created_files: list[Path] = []

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        path = save_batch(
            batch_number=batch_number,
            entries=batch,
        )

        created_files.append(path)

        print(
            f"{path.name}: "
            f"{len(batch)} записей"
        )

    manifest_path = (
        BATCHES_DIR
        / "manifest.json"
    )

    manifest = {
        "schema_version": 1,
        "source_file": str(
            SOURCE_PATH.relative_to(BASE_DIR)
        ),
        "batch_size": BATCH_SIZE,
        "total_entries": len(prepared_entries),
        "total_batches": len(batches),
        "files": [
            path.name
            for path in created_files
        ],
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(f"Манифест: {manifest_path}")
    print("Рабочие пакеты созданы")


if __name__ == "__main__":
    main()