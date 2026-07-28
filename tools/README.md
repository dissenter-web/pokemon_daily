# Pokemon Daily editorial generator

Автоматически:

- читает `missing_pokemon.csv`;
- получает исходные английские записи Pokédex из PokéAPI;
- создаёт русские `name_ru`, `description_ru`, `fact_ru`;
- сохраняет прогресс после каждого пакета;
- формирует `generation_1.json` ... `generation_9.json`;
- сохраняет уже готовые первые девять записей.

## Установка

```bash
python -m pip install "openai>=1.0" "requests>=2.31"
```

## Переменная окружения

```bash
export OPENAI_API_KEY="твой_api_ключ"
```

При необходимости:

```bash
export OPENAI_MODEL="gpt-5-mini"
```

## Тест на трёх покемонах

Запускать из корня проекта:

```bash
python tools/generate_editorial.py \
  --missing-csv missing_pokemon.csv \
  --existing-json data/editorial/generation_1.json \
  --output-dir data/editorial \
  --max-items 3
```

## Полный запуск

```bash
python tools/generate_editorial.py \
  --missing-csv missing_pokemon.csv \
  --existing-json data/editorial/generation_1.json \
  --output-dir data/editorial \
  --batch-size 10
```

Повторный запуск продолжит работу из:

```text
data/editorial/.editorial_checkpoint.json
```

После завершения проверь:

```bash
python - <<'PY'
import json
from pathlib import Path

total = 0
for path in sorted(Path("data/editorial").glob("generation_*.json")):
    count = len(json.loads(path.read_text(encoding="utf-8"))["entries"])
    print(path.name, count)
    total += count

print("TOTAL:", total)
PY
```

Затем пересобери контейнеры и запусти синхронизацию каталога.
