#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI


GENERATION_RANGES = {
    1: (1, 151),
    2: (152, 251),
    3: (252, 386),
    4: (387, 493),
    5: (494, 649),
    6: (650, 721),
    7: (722, 809),
    8: (810, 905),
    9: (906, 1025),
}


@dataclass(frozen=True)
class PokemonRow:
    pokeapi_id: int
    slug: str
    name_en: str
    source_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Russian editorial JSON files for Pokemon Daily."
    )
    parser.add_argument(
        "--missing-csv",
        type=Path,
        default=Path("missing_pokemon.csv"),
    )
    parser.add_argument(
        "--existing-json",
        type=Path,
        default=Path("data/editorial/generation_1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/editorial"),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Pause between API batches in seconds.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Generate only the first N missing entries for a test run.",
    )
    return parser.parse_args()


def load_missing_rows(path: Path) -> list[PokemonRow]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    rows: list[PokemonRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"pokeapi_id", "slug", "name_en", "source_url"}
        actual = set(reader.fieldnames or [])
        missing = required - actual
        if missing:
            raise ValueError(
                f"CSV is missing columns: {', '.join(sorted(missing))}"
            )

        for raw in reader:
            rows.append(
                PokemonRow(
                    pokeapi_id=int(raw["pokeapi_id"]),
                    slug=raw["slug"].strip(),
                    name_en=raw["name_en"].strip(),
                    source_url=raw["source_url"].strip(),
                )
            )

    return rows


def load_existing_entries(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError(f"{path} must contain an entries object")
    return entries


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").replace("\f", " ").split())


def fetch_species_context(
    session: requests.Session,
    row: PokemonRow,
    retries: int = 5,
) -> dict[str, Any]:
    delay = 1.0

    for attempt in range(1, retries + 1):
        try:
            response = session.get(row.source_url, timeout=30)
            response.raise_for_status()
            payload = response.json()

            flavor_texts = []
            for item in payload.get("flavor_text_entries", []):
                language = item.get("language", {}).get("name")
                if language != "en":
                    continue
                text = normalize_text(item.get("flavor_text", ""))
                if text and text not in flavor_texts:
                    flavor_texts.append(text)

            genera = []
            for item in payload.get("genera", []):
                language = item.get("language", {}).get("name")
                if language == "en":
                    genus = normalize_text(item.get("genus", ""))
                    if genus:
                        genera.append(genus)

            return {
                "pokeapi_id": row.pokeapi_id,
                "slug": row.slug,
                "name_en": row.name_en,
                "source_url": row.source_url,
                "genus_en": genera[0] if genera else "",
                "flavor_texts_en": flavor_texts[-8:],
                "habitat": (
                    payload.get("habitat", {}).get("name")
                    if payload.get("habitat")
                    else None
                ),
                "shape": (
                    payload.get("shape", {}).get("name")
                    if payload.get("shape")
                    else None
                ),
                "is_legendary": bool(payload.get("is_legendary")),
                "is_mythical": bool(payload.get("is_mythical")),
            }

        except (requests.RequestException, ValueError) as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Failed to load PokeAPI data for {row.slug}: {exc}"
                ) from exc
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"Unexpected retry failure for {row.slug}")


def response_schema() -> dict[str, Any]:
    entry_schema = {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "name_ru": {"type": "string"},
            "description_ru": {"type": "string"},
            "fact_ru": {"type": "string"},
        },
        "required": ["slug", "name_ru", "description_ru", "fact_ru"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "items": entry_schema,
            }
        },
        "required": ["entries"],
        "additionalProperties": False,
    }


def generate_batch(
    client: OpenAI,
    model: str,
    contexts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    instructions = """
Ты создаёшь редакторский контент для русскоязычного сервиса Pokemon Daily.

Для каждого покемона:
1. name_ru: общепринятая русская транскрипция имени.
2. description_ru: одно короткое естественное предложение, 90–180 символов.
3. fact_ru: один отдельный интересный факт, 70–170 символов.
4. Используй только факты из переданных английских записей Pokédex и метаданных.
5. Не выдумывай способности, размеры, поведение или происхождение.
6. Не копируй описание дословно в fact_ru.
7. Не используй канцелярит, кавычки вокруг имени и маркетинговые формулировки.
8. Верни запись для каждого slug ровно один раз.
"""

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=json.dumps(contexts, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "pokemon_editorial_batch",
                "strict": True,
                "schema": response_schema(),
            }
        },
    )

    payload = json.loads(response.output_text)
    entries = payload["entries"]

    expected = {item["slug"] for item in contexts}
    actual = {item["slug"] for item in entries}

    if expected != actual:
        raise ValueError(
            "Model returned a different slug set. "
            f"Missing: {sorted(expected - actual)}; "
            f"extra: {sorted(actual - expected)}"
        )

    return entries


def generation_for_id(pokeapi_id: int) -> int:
    for generation, (start, end) in GENERATION_RANGES.items():
        if start <= pokeapi_id <= end:
            return generation
    raise ValueError(f"Unsupported National Pokédex id: {pokeapi_id}")


def write_generation_files(
    output_dir: Path,
    rows_by_slug: dict[str, PokemonRow],
    all_entries: dict[str, dict[str, str]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    generation_entries: dict[int, dict[str, dict[str, str]]] = {
        number: {} for number in GENERATION_RANGES
    }

    for slug, content in all_entries.items():
        row = rows_by_slug.get(slug)
        if row is None:
            # Existing first-nine entries may not be in missing_pokemon.csv.
            source_url = content.get("source_url", "")
            try:
                pokeapi_id = int(source_url.rstrip("/").split("/")[-1])
            except (ValueError, IndexError):
                raise ValueError(
                    f"Cannot determine PokeAPI id for existing slug '{slug}'"
                )
        else:
            pokeapi_id = row.pokeapi_id

        generation = generation_for_id(pokeapi_id)
        generation_entries[generation][slug] = content

    for generation, entries in generation_entries.items():
        if not entries:
            continue

        ordered = dict(
            sorted(
                entries.items(),
                key=lambda item: int(
                    item[1]["source_url"].rstrip("/").split("/")[-1]
                ),
            )
        )

        payload = {
            "schema_version": 1,
            "language": "ru",
            "editorial_policy": (
                "Краткий пересказ проверяемых записей Pokédex "
                "без генерации текста внутри приложения."
            ),
            "entries": ordered,
        }

        path = output_dir / f"generation_{generation}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def save_checkpoint(
    path: Path,
    entries: dict[str, dict[str, str]],
) -> None:
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is not set. Export it before running.",
            file=sys.stderr,
        )
        return 2

    rows = load_missing_rows(args.missing_csv)
    if args.max_items is not None:
        rows = rows[: args.max_items]

    existing_entries = load_existing_entries(args.existing_json)
    rows_by_slug = {row.slug: row for row in rows}

    checkpoint_path = args.output_dir / ".editorial_checkpoint.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_entries: dict[str, dict[str, str]] = {}
    if checkpoint_path.exists():
        checkpoint_entries = json.loads(
            checkpoint_path.read_text(encoding="utf-8")
        )

    all_entries = {**existing_entries, **checkpoint_entries}
    pending_rows = [row for row in rows if row.slug not in all_entries]

    print(f"Existing entries: {len(existing_entries)}")
    print(f"Checkpoint entries: {len(checkpoint_entries)}")
    print(f"Pending entries: {len(pending_rows)}")

    if not pending_rows:
        write_generation_files(args.output_dir, rows_by_slug, all_entries)
        print("Nothing to generate. Files rebuilt from existing data.")
        return 0

    client = OpenAI()
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "PokemonDailyEditorialGenerator/1.0"}
    )

    for batch_start in range(0, len(pending_rows), args.batch_size):
        batch_rows = pending_rows[
            batch_start : batch_start + args.batch_size
        ]

        contexts = [
            fetch_species_context(session, row)
            for row in batch_rows
        ]

        generated = generate_batch(client, args.model, contexts)

        for item in generated:
            slug = item["slug"]
            row = rows_by_slug[slug]
            all_entries[slug] = {
                "name_ru": item["name_ru"].strip(),
                "description_ru": item["description_ru"].strip(),
                "fact_ru": item["fact_ru"].strip(),
                "source_url": row.source_url,
            }

        generated_only = {
            slug: content
            for slug, content in all_entries.items()
            if slug not in existing_entries
        }
        save_checkpoint(checkpoint_path, generated_only)
        write_generation_files(
            args.output_dir,
            rows_by_slug,
            all_entries,
        )

        completed = min(
            batch_start + len(batch_rows),
            len(pending_rows),
        )
        print(
            f"Generated {completed}/{len(pending_rows)} pending entries"
        )

        if args.sleep:
            time.sleep(args.sleep)

    print(
        f"Done. Total editorial entries: {len(all_entries)}. "
        f"Files: {args.output_dir}/generation_*.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
