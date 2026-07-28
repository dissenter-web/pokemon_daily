from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
BATCHES_DIR = BASE_DIR / "data" / "editorial_batches"
EDITORIAL_DIR = BASE_DIR / "data" / "editorial"

MANIFEST_PATH = BATCHES_DIR / "manifest.json"
OUTPUT_PATH = EDITORIAL_DIR / "generation_2.json"


def load_json(path: Path) -> dict[str, Any]:
    """
    Загружает JSON-файл и проверяет,
    что корневое значение является объектом.
    """
    try:
        raw_data = path.read_text(encoding="utf-8")
        data = json.loads(raw_data)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Файл не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Некорректный JSON в файле {path}: "
            f"строка {exc.lineno}, столбец {exc.colno}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Корневое значение JSON должно быть объектом: {path}"
        )

    return data


def validate_text(value: Any, field_name: str, slug: str) -> str:
    """
    Проверяет обязательное текстовое поле карточки.
    """
    if not isinstance(value, str):
        raise RuntimeError(
            f"{slug}: поле {field_name!r} должно быть строкой"
        )

    value = value.strip()

    if not value:
        raise RuntimeError(
            f"{slug}: поле {field_name!r} не заполнено"
        )

    return value


def get_batch_paths(manifest: dict[str, Any]) -> list[Path]:
    """
    Получает список файлов батчей из manifest.json.
    """
    batches = manifest.get("files")

    if not isinstance(batches, list):
        raise RuntimeError(
            "В manifest.json поле 'files' должно быть массивом"
        )

    paths: list[Path] = []

    for item in batches:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                "Каждый элемент manifest.files должен быть именем файла"
            )

        paths.append(BATCHES_DIR / item)

    if not paths:
        raise RuntimeError("В manifest.json не указаны файлы батчей")

    return paths


def compile_editorial_entries(
    batch_paths: list[Path],
) -> dict[str, dict[str, Any]]:
    """
    Собирает записи из переводных батчей
    в формат рабочего editorial-реестра.
    """
    compiled_entries: dict[str, dict[str, Any]] = {}

    used_pokeapi_ids: set[int] = set()

    for batch_path in batch_paths:
        batch = load_json(batch_path)

        batch_status = batch.get("status")

        if batch_status != "ready":
            raise RuntimeError(
                f"{batch_path.name}: верхний status должен быть 'ready', "
                f"получено {batch_status!r}"
            )

        entries = batch.get("entries")

        if not isinstance(entries, list):
            raise RuntimeError(
                f"{batch_path.name}: поле 'entries' должно быть массивом"
            )

        declared_total = batch.get("total")

        if declared_total != len(entries):
            raise RuntimeError(
                f"{batch_path.name}: поле total={declared_total!r}, "
                f"но фактически записей {len(entries)}"
            )

        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError(
                    f"{batch_path.name}: каждая запись должна быть объектом"
                )

            slug = validate_text(
                entry.get("slug"),
                "slug",
                batch_path.name,
            )

            pokeapi_id = entry.get("pokeapi_id")

            if not isinstance(pokeapi_id, int) or pokeapi_id <= 0:
                raise RuntimeError(
                    f"{slug}: поле 'pokeapi_id' должно быть "
                    "положительным целым числом"
                )

            entry_status = entry.get("status")

            if entry_status != "ready":
                raise RuntimeError(
                    f"{slug}: status должен быть 'ready', "
                    f"получено {entry_status!r}"
                )

            if slug in compiled_entries:
                raise RuntimeError(
                    f"Найден повторяющийся slug: {slug}"
                )

            if pokeapi_id in used_pokeapi_ids:
                raise RuntimeError(
                    f"Найден повторяющийся pokeapi_id: {pokeapi_id}"
                )

            name_ru = validate_text(
                entry.get("name_ru"),
                "name_ru",
                slug,
            )

            description_ru = validate_text(
                entry.get("description_ru"),
                "description_ru",
                slug,
            )

            fact_ru = validate_text(
                entry.get("fact_ru"),
                "fact_ru",
                slug,
            )

            source_url = validate_text(
                entry.get("source_url"),
                "source_url",
                slug,
            )

            compiled_entries[slug] = {
                "pokeapi_id": pokeapi_id,
                "name_ru": name_ru,
                "description_ru": description_ru,
                "fact_ru": fact_ru,
                "source_url": source_url,
            }

            used_pokeapi_ids.add(pokeapi_id)

    return compiled_entries


def save_compiled_file(
    entries: dict[str, dict[str, Any]],
) -> None:
    """
    Сохраняет собранный рабочий editorial-файл.
    """
    EDITORIAL_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "language": "ru",
        "status": "ready",
        "total": len(entries),
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
    manifest = load_json(MANIFEST_PATH)

    batch_paths = get_batch_paths(manifest)

    entries = compile_editorial_entries(batch_paths)

    save_compiled_file(entries)

    print(f"Собрано редакционных записей: {len(entries)}")
    print(f"Рабочий файл создан: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()