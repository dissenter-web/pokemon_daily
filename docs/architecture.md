# Архитектура Pokémon Daily

## Границы системы

Это модульный монолит с тремя точками запуска:

1. `app.main` — FastAPI, health endpoints и MAX webhook.
2. `app.worker` — планирование и отправка ежедневных карточек.
3. `app.cli` — синхронизация каталога, ручной запуск delivery и регистрация webhook.

API и worker используют одну PostgreSQL, но запускаются отдельными процессами.
Это не микросервисы: код, модели и релизный цикл у них общие.

## Структура каталогов

```text
app/
├── api/            HTTP endpoint и зависимости FastAPI
├── bot/            кнопки и форматирование MAX-сообщений
├── clients/        MAX API и PokéAPI
├── db/             SQLAlchemy metadata, модели и AsyncSession
├── domain/         сущности, enum и ошибки без инфраструктуры
├── repositories/   только SQL-запросы и сохранение
├── schemas/        Pydantic-модели входящих событий
├── services/       бизнес-сценарии
├── cli.py          служебные команды
├── main.py         FastAPI process
└── worker.py       delivery process
```

Endpoint не выбирает покемона и не меняет коллекцию напрямую. MAX client ничего
не знает о пользователях и прогрессе. Repository не решает, кому и когда выдавать
карточку.

## Поток webhook

```text
MAX
  |
  | HTTPS POST + X-Max-Bot-Api-Secret
  v
Nginx :443
  |
  v
FastAPI /webhook/max
  |-- ограничение body
  |-- constant-time проверка secret
  |-- Pydantic validation
  v
WebhookService
  |-- INSERT processed_webhook_updates (unique update_key)
  |-- get-or-create User
  |-- callback payload -> внутренняя команда
  v
CollectionService / DeliveryService
  |                         |
  v                         v
PostgreSQL              MaxAPIClient
                            |
                            v
                           MAX
```

`update_key` строится из event-specific идентификатора (`callback_id` или
message `mid`) и SHA-256. Если такого ID нет, хешируется канонический JSON вместе
с типом и timestamp. Уникальный индекс блокирует повторное действие.

Перед внешним side effect событие резервируется со статусом `processing`.
После успеха становится `processed`. Неопределённая внешняя ошибка сохраняется
как `failed` и автоматически не повторяется: MAX мог уже выполнить запрос.
Для ошибки соединения до отправки reservation освобождается, и повтор MAX безопасен.

## Поток ежедневной карточки

```text
worker tick
  |
  | local time >= DAILY_DELIVERY_TIME
  v
active users without delivery for local date
  |
  | lock User + choose first unopened content-ready Pokemon
  v
INSERT daily_deliveries (user_id, delivery_date) UNIQUE
  | status=pending
  v
atomic UPDATE pending/retryable -> sending
  | attempt_count += 1
  v
load local card from PostgreSQL
  |
  v
POST platform-api2.max.ru/messages
  |
  +-- success -> INSERT user_collections + delivery=sent
  |
  +-- definite temporary failure -> retryable + next_attempt_at
  |
  +-- ambiguous result -> permanently_failed, no automatic resend
```

Выбор следующего покемона сортирует:

1. `evolution_chains.sequence_order`;
2. `evolution_stages.stage_order` — глубина дерева;
3. `evolution_stages.branch_order` — стабильный DFS-порядок по PokéAPI ID;
4. `pokemon.pokeapi_id`.

Затем исключаются уже существующие пары `(user_id, pokemon_id)` из коллекции.

## Почему отдельный PostgreSQL-backed worker

| Вариант | Решение |
|---|---|
| APScheduler внутри FastAPI | Не выбран: несколько API-replica создадут несколько scheduler-экземпляров; жизненный цикл связан с web process |
| system cron | Пригоден для одного VPS, но хуже выражает retry-state и атомарный захват задания |
| Celery + Redis | Надёжен, но для масштаба проекта добавляет два компонента и двойное хранилище состояния без необходимости |
| отдельный worker + PostgreSQL | Выбран: не блокирует FastAPI, переживает рестарт, использует уже обязательную БД и масштабируется несколькими worker |

Worker не «спит до восьми утра». Он периодически ищет фактическое состояние в БД.
После рестарта пропущенные `pending/retryable` задания продолжаются.

Если временный сбой переносит задание на следующие сутки, новый Pokémon для этого
пользователя не резервируется. Старое задание используется повторно, а при
атомарном claim его `delivery_date` переносится на текущую локальную дату. Поэтому
после позднего успешного повтора worker не создаст вторую новую карточку в те же
сутки, а пользователь продолжит последовательность без пропуска.

## Транзакции и идемпотентность

База обеспечивает:

- один MAX user: `UNIQUE users.max_user_id`;
- одну выдачу на сутки: `UNIQUE (daily_deliveries.user_id, delivery_date)`;
- отсутствие повторов коллекции: `UNIQUE (user_collections.user_id, pokemon_id)`;
- отсутствие дублей избранного: `UNIQUE (favorites.user_id, pokemon_id)`;
- одно действие webhook: `UNIQUE processed_webhook_updates.update_key`.

Проверки в Python улучшают ответ пользователю, но окончательную защиту даёт БД.

MAX API не документирует idempotency key для `POST /messages`, поэтому абсолютное
«exactly once» между двумя системами математически недостижимо без поддержки
провайдера. Политика проекта ориентирована на отсутствие дублей:

- 429, 503, connect error и connect timeout повторяются;
- read/write timeout, разрыв протокола и неожиданный 5xx считаются неоднозначными;
- зависшее `sending` переводится в `permanently_failed`, а не отправляется снова.

Компромисс: при падении worker ровно после успешного MAX-запроса, но до фиксации
ответа в PostgreSQL, пользователь может не получить запись в коллекции. Зато бот
не отправит скрытый дубль. Оператор видит `error_code` и может разбирать случай.

Официальный предел MAX — 30 запросов в секунду. Каждый из двух исходящих
процессов ограничен десятью запросами в секунду, поэтому стандартный deployment
API + worker остаётся ниже общего лимита. При горизонтальном масштабировании
число replica нужно учитывать либо заменить локальный limiter распределённым.

## SQLAlchemy, PostgreSQL и Alembic

SQLAlchemy-модель — Python-описание таблиц и отношений. PostgreSQL фактически
хранит данные и исполняет ограничения, блокировки и транзакции. `AsyncSession`
накапливает изменения до `commit`; `rollback` отменяет незавершённую транзакцию.

Alembic не создаёт БД «из текущих моделей» при каждом старте. Миграция
`0001_initial.py` — неизменяемая версия схемы. Следующее изменение модели требует
новой миграции, которую можно проверить и применить командой `alembic upgrade head`.

## Модель данных

| Область | Таблицы |
|---|---|
| Пользователь | `users` |
| Каталог | `pokemon_species`, `pokemon`, `types`, `abilities`, связующие таблицы |
| Эволюция | `evolution_chains`, `evolution_stages` |
| Прогресс | `daily_deliveries`, `user_collections`, `favorites` |
| Идемпотентность | `processed_webhook_updates` |
| Обслуживание | `sync_runs` |

Время хранится timezone-aware в UTC. Календарная дата выдачи вычисляется через
`APP_TIMEZONE` и сохраняется отдельно в `delivery_date`.

## Синхронизация каталога

```text
PokéAPI evolution-chain list
  |
  v
chain tree -> deterministic flatten
  |
  +--> species + default Pokemon + types + abilities + official artwork URL
  |
  +--> local editorial_content.ru.json
  v
PostgreSQL upsert + integrity constraints
```

PokéAPI вызывается только служебной командой. Полученные ресурсы кешируются в
памяти одного запуска и сохраняются нормализованно в PostgreSQL. Daily delivery
не обращается к PokéAPI.

Редакционный JSON отделён от внешних полей. Карточка становится доступной только
при наличии русского имени, описания и факта. Источник каждой записи хранится в
`content_source_url`.

## Изображения

Используется URL `official-artwork` из PokéAPI sprites. MAX официально разрешает
`attachments.payload.url` для изображений. Если MAX определённо отклоняет
image-attachment с HTTP 400, клиент повторяет тот же запрос без изображения.
Неопределённая ошибка не запускает fallback, потому что первое сообщение могло
быть доставлено.

Даже при недоступности PokéAPI карточка формируется из PostgreSQL. Недоступность
image CDN влияет только на изображение; текст остаётся самостоятельной карточкой.

## Расширение

- Новый русский контент: добавить запись в JSON и повторить sync.
- Персональный часовой пояс: добавить timezone в `users` и вычислять
  `delivery_date` по нему.
- Несколько worker: текущий conditional `UPDATE` допускает горизонтальный запуск.
- Локальные изображения: добавить media cache и публичный read-only route,
  не меняя delivery-правило.
- Метрики: добавить Prometheus только после появления реальной потребности.
