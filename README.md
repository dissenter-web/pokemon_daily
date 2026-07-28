# Pokémon Daily

Production-подобный учебный backend-проект: MAX-бот ежедневно выдаёт пользователю
нового покемона в воспроизводимом порядке эволюционных цепочек.

Проект некоммерческий и не связан с Nintendo, Game Freak или The Pokémon Company.
Названия Pokémon и персонажей являются товарными знаками их правообладателей.

На дату проектирования MAX разрешает создание и публикацию API-бота через
верифицированный профиль организации, ИП или самозанятого — резидента РФ; доступ
пользователей появляется после модерации. Это внешнее организационное требование,
а не ограничение кода:
[официальная подготовка MAX-бота](https://dev.max.ru/docs/chatbots/bots-coding/prepare).

## Что реализовано

- FastAPI webhook с проверкой `X-Max-Bot-Api-Secret`;
- автоматическая регистрация по `MAX user_id` без сбора лишних данных;
- карточка дня, коллекция, пагинация, избранное, статистика и меню без slash-команд;
- не более одной новой карточки в календарные сутки;
- порядок `эволюционная цепочка → глубина этапа → стабильный порядок ветки`;
- PostgreSQL-ограничения против дублей;
- отдельный delivery-worker с безопасными повторными попытками;
- локальный нормализованный каталог и отдельный редакционный русский контент;
- синхронизация PokéAPI отдельной CLI-командой;
- прямое изображение по HTTPS с текстовым fallback;
- Alembic, Docker Compose, Nginx, healthchecks и JSON-логи;
- стартовый проверенный русский контент для первых девяти покемонов;
- unit-тесты ключевых правил и проверка ограничений модели БД.

## Быстрый локальный запуск

Требуются Docker Engine с Compose v2 и свободный порт `8000`.

```bash
cp .env.example .env
```

В `.env` минимум замените:

```dotenv
POSTGRES_PASSWORD=сильный_пароль
DATABASE_URL=postgresql+asyncpg://pokemon_daily:сильный_пароль@db:5432/pokemon_daily
MAX_BOT_TOKEN=токен_бота
MAX_WEBHOOK_SECRET=случайная_строка_без_пробелов
PUBLIC_BASE_URL=https://bot.example.com
```

Добавьте сертификаты Минцифры в `certs/`, затем:

```bash
docker compose up --build -d
docker compose exec app python -m app.cli sync-catalog --max-chains 3
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`--max-chains 3` загружает три стартовые цепочки и девять готовых русских
карточек. Для синхронизации всех цепочек:

```bash
docker compose exec app python -m app.cli sync-catalog
```

Покемоны без заполненных `description_ru` и `fact_ru` сохраняются в каталоге,
но не попадают в выдачу. Поэтому расширение коллекции безопасно выполняется через
`data/editorial` и повторную синхронизацию.

## Production-запуск

Полная инструкция для чистого Ubuntu VPS: [docs/deployment.md](docs/deployment.md).

После настройки домена, TLS и `nginx/pokemon_daily.conf`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
docker compose exec app python -m app.cli sync-catalog --max-chains 3
docker compose exec app python -m app.cli register-webhook
```

MAX принимает production webhook только по HTTPS на порту `443`. Самоподписанный
сертификат не подходит.

## Основные команды

```bash
docker compose ps
docker compose logs -f app worker
docker compose exec app alembic current
docker compose exec app alembic upgrade head
docker compose exec worker python -m app.cli delivery-run
docker compose down
```

Локальные проверки:

```bash
python -m pip install -e ".[dev]"
ruff check app tests
pytest
python -m compileall -q app tests migrations
```

PostgreSQL integration-test создаёт и затем удаляет отдельную случайную схему:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost/test_db \
  pytest -m integration
```

Резервная копия:

```bash
mkdir -p backups
docker compose exec -T db pg_dump \
  -U pokemon_daily -d pokemon_daily -Fc > backups/pokemon_daily.dump
```

Восстановление в пустую или специально выбранную базу:

```bash
docker compose exec -T db pg_restore \
  -U pokemon_daily -d pokemon_daily --clean --if-exists \
  < backups/pokemon_daily.dump
```

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `ENVIRONMENT` | `development`, `test` или `production` |
| `DATABASE_URL` | Async SQLAlchemy URL с драйвером `asyncpg` |
| `APP_TIMEZONE` | Часовой пояс календарных суток |
| `DAILY_DELIVERY_TIME` | Время автоматической выдачи, `HH:MM` |
| `MAX_BOT_TOKEN` | Секретный токен MAX, только через окружение |
| `MAX_WEBHOOK_SECRET` | Секрет заголовка webhook |
| `MAX_API_BASE_URL` | По умолчанию `https://platform-api2.max.ru` |
| `MAX_CA_BUNDLE` | CA bundle для исходящего TLS |
| `PUBLIC_BASE_URL` | Публичный HTTPS-домен без пути |
| `WEBHOOK_MAX_BODY_BYTES` | Максимальный размер webhook-body |
| `POKEAPI_BASE_URL` | REST API каталога |
| `EDITORIAL_CONTENT_PATH` | Каталог с русским редакционным контентом |

Полный список и безопасные примеры находятся в `.env.example`.

## Источники и подтверждённые ограничения

- MAX рекомендует webhook для production, требует HTTPS/443, доверенный сертификат,
  полный certificate chain и ответ не позднее 30 секунд:
  [POST /subscriptions](https://dev.max.ru/docs-api/methods/POST/subscriptions).
- Актуальный исходящий домен — `platform-api2.max.ru`; токен передаётся заголовком
  `Authorization`: [POST /messages](https://dev.max.ru/docs-api/methods/POST/messages).
- Изображение разрешено передавать внешним URL; лимит загружаемого изображения —
  50 МБ и 7680×7680:
  [POST /uploads](https://dev.max.ru/docs-api/methods/POST/uploads).
- PokéAPI описывает цепочку как дерево от базового вида к следующим этапам:
  [Evolution Chains](https://pokeapi.co/docs/v2#evolution-chains).
- PokéAPI просит локально кешировать запрашиваемые ресурсы:
  [Fair Use](https://pokeapi.co/docs/graphql#fair-use).
- На дату проектирования стабильная ветка Python — 3.14:
  [Python downloads](https://www.python.org/downloads/).

## Документация

- [Архитектура и потоки данных](docs/architecture.md)
- [Развёртывание, TLS, webhook, backup/restore](docs/deployment.md)
