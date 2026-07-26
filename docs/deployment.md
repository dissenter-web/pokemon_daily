# Развёртывание на Ubuntu VPS

## 1. Сервер и DNS

Минимально: Ubuntu 24.04 LTS, 2 ГБ RAM, домен с A/AAAA-записью на VPS, открытые
TCP-порты `22`, `80`, `443`. Установите Docker Engine и Compose v2 по
[официальной инструкции Docker для Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

До технического deployment подготовьте верифицированный профиль MAX. По
актуальной документации создать бота могут организации, ИП и самозанятые —
резиденты РФ, а публичный доступ появляется после модерации:
[подготовка MAX-бота](https://dev.max.ru/docs/chatbots/bots-coding/prepare).

Клонируйте проект, перейдите в каталог и создайте конфигурацию:

```bash
cp .env.example .env
chmod 600 .env
```

Установите `ENVIRONMENT=production`, сильные пароль БД и webhook secret, токен
MAX и реальный `PUBLIC_BASE_URL`. Пароль в `DATABASE_URL` должен совпадать с
`POSTGRES_PASSWORD`.

## 2. Входящий HTTPS

MAX требует доступный HTTPS endpoint строго на порту 443, совпадение домена с
CN/SAN, полную цепочку и сертификат доверенного CA; самоподписанный сертификат
не принимается.

Получите сертификат у выбранного доверенного CA. В production Compose ожидаются:

```text
secrets/tls/fullchain.pem
secrets/tls/privkey.pem
```

Production Compose использует официальный unprivileged Nginx-образ с UID/GID
`101`. Дайте этому пользователю чтение ключа, не открывая его остальным:

```bash
sudo chown 101:101 secrets/tls/privkey.pem
chmod 600 secrets/tls/privkey.pem
chmod 644 secrets/tls/fullchain.pem
```

Замените `bot.example.com` в `nginx/pokemon_daily.conf` на реальный домен.

Проверка полной внешней цепочки:

```bash
openssl s_client -connect bot.example.com:443 \
  -servername bot.example.com -showcerts </dev/null
```

## 3. Исходящий TLS к MAX и сертификаты Минцифры

MAX требует запросы на `platform-api2.max.ru` и доверие к сертификатам Минцифры.
Скачайте корневой и промежуточный сертификаты только из доверенного официального
источника и сверьте опубликованные отпечатки.

Если исходный файл в DER:

```bash
openssl x509 -inform DER -in russian_trusted_root_ca.cer \
  -out certs/russian_trusted_root_ca.pem
openssl x509 -inform DER -in russian_trusted_sub_ca.cer \
  -out certs/russian_trusted_sub_ca.pem
```

Если файл уже PEM, достаточно расширения `.pem`. Сертификаты не коммитятся.
Entrypoint каждого Python-контейнера копирует системный CA bundle и добавляет
файлы `certs/*.pem`, `*.cer`, `*.crt` в `/tmp/max-ca-bundle.pem`.

Проверка TLS и токена без их вывода:

```bash
docker compose exec app python -c \
'import httpx; from app.config import get_settings; s=get_settings(); r=httpx.get(s.max_api_base_url+"/me", headers={"Authorization":s.max_bot_token.get_secret_value()}, verify=str(s.max_ca_bundle), timeout=10); print(r.status_code)'
```

Ожидается `200`. `401` означает проблему токена, TLS exception — проблему bundle
или certificate chain. В проекте нигде не используется `verify=False`.

## 4. Запуск

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up --build -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Сервис `migrate` дождётся PostgreSQL и выполнит `alembic upgrade head`; API и
worker стартуют только после успешной миграции.

Проверки:

```bash
curl -fsS https://bot.example.com/health
curl -fsS https://bot.example.com/ready
docker compose logs --tail=100 app worker
```

## 5. Начальный каталог

```bash
docker compose exec app python -m app.cli sync-catalog --max-chains 3
```

Команда загружает первые три цепочки. В репозитории есть русский редакционный
контент для девяти соответствующих покемонов. Полная внешняя синхронизация:

```bash
docker compose exec app python -m app.cli sync-catalog
```

Полная команда может выполняться долго: она уважает fair-use PokéAPI и сохраняет
каждый ресурс локально. Покемоны без русского редакционного контента не выдаются.

## 6. Регистрация webhook

В `.env`:

```dotenv
PUBLIC_BASE_URL=https://bot.example.com
WEBHOOK_PATH=/webhook/max
MAX_WEBHOOK_SECRET=случайная_строка_A-Za-z0-9_-
```

Регистрация:

```bash
docker compose exec app python -m app.cli register-webhook
```

Команда подписывает бота на `bot_started`, `bot_stopped`, `dialog_removed`,
`message_created`, `message_callback`. MAX будет отправлять secret в
`X-Max-Bot-Api-Secret`, приложение сравнивает его constant-time.

Официальные требования:
[MAX POST /subscriptions](https://dev.max.ru/docs-api/methods/POST/subscriptions).

## 7. Проверка сценариев

1. Откройте бота и нажмите старт — должно появиться кнопочное меню.
2. Нажмите «Покемон дня» — приходит Бульбазавр.
3. Нажмите повторно — новая карточка не создаётся.
4. Добавьте карточку в избранное и проверьте раздел.
5. Откройте коллекцию и статистику.
6. Запустите `python -m app.cli delivery-run` дважды — уникальная дата и
   conditional claim не допускают вторую новую выдачу.
7. Проверьте JSON-логи без токенов и персональных полей.

## 8. Обновление

Перед обновлением сделайте backup:

```bash
mkdir -p backups
docker compose exec -T db pg_dump \
  -U pokemon_daily -d pokemon_daily -Fc \
  > "backups/pokemon_daily-$(date +%F).dump"
```

Затем:

```bash
git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up --build -d
```

## 9. Восстановление

Остановите API и worker, но оставьте БД:

```bash
docker compose stop app worker
docker compose exec -T db pg_restore \
  -U pokemon_daily -d pokemon_daily --clean --if-exists \
  < backups/pokemon_daily-YYYY-MM-DD.dump
docker compose start app worker
```

## 10. Эксплуатационные ограничения первой версии

- Локальный русский контент готов для девяти стартовых карточек.
- URL изображения зависит от PokeAPI sprites CDN; текст имеет fallback.
- Неопределённый результат MAX не повторяется автоматически во избежание дубля.
  Такие доставки имеют `permanently_failed` и требуют просмотра логов/БД.
- Отдельная административная панель намеренно отсутствует.
