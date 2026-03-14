# FastAPI-Shortcut-Link

## Содержание

- [Запуск](#запуск)
- [Тестирование](#тестирование)
- [База данных](#база-данных)
- [auth.py](#authpy)
- [links.py](#linkspy)

## Запуск

Создайте `api/.env`:

```
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/short_links
REDIS_URL=redis://redis:6379
```

```bash
docker compose up --build
```

API: http://localhost:8000
Swagger: http://localhost:8000/docs

## Тестирование

### Установка зависимостей

```bash
pip install -r api/requirements.txt
pip install -r tests/requirements.txt
```

### Запуск тестов

Из корня репозитория:

```bash
python -m pytest tests/
```

### Покрытие кода

[Готовый отчёт](./htmlcov/index.html)

```bash
# тесты с замером покрытия
python -m coverage run --rcfile tests/.coveragerc -m pytest tests/

# краткий отчёт в терминале
python -m coverage report --rcfile tests/.coveragerc -m

# HTML-отчёт
python -m coverage html --rcfile tests/.coveragerc
```

### Нагрузочные тесты

Сервис должен быть запущен (`docker compose up`):

```bash
# интерактивный UI (http://localhost:8089)
python -m locust -f tests/locustfile.py --host http://localhost:8000

# консоль 50 user, 10 rate/sec, 60 sec
python -m locust -f tests/locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 --run-time 60s
```

### Структура тестов

```
tests/
├── conftest.py       # тестовая БД + мок Redis
├── test_unit.py      # юнит-тесты
├── test_auth.py      # /register, /login
├── test_links.py     # Link CRUD ручки
├── locustfile.py     # нагрузочные сценарии
├── requirements.txt  # зависимости
└── .coveragerc       # конфигурация coverage
```

## База данных

Таблица `users`

| Колонка | Тип | Описание |
|---|---|---|
| id | INTEGER | PK |
| username | VARCHAR | уникальный |
| hashed_password | VARCHAR | bcrypt |

Таблица `links`

| Колонка | Тип | Описание |
|---|---|---|
| id | INTEGER | PK |
| short_code | VARCHAR | уникальный, индекс |
| original_url | VARCHAR | |
| custom_alias | VARCHAR | nullable, unique |
| created_at | DATETIME | |
| expires_at | DATETIME | nullable |
| clicks_count | INTEGER | default 0 |
| last_used_at | DATETIME | nullable |
| project | VARCHAR | nullable |
| user_id | INTEGER | FK -> users.id, nullable |

user_id = NULL означает анонимную ссылку.

Redis кеширует short_code -> original_url с TTL 3600 с. Истёкшие пишутся как "EXPIRED".

## auth.py

JWT Bearer, токен живёт 24 часа. Заголовок: `Authorization: Bearer <token>`

Валидация: username минимум 3 символа, password минимум 6.

### POST /register

```bash
# успех
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"hse.student","password":"hse.pass123"}'
# {"message":"Registered"}

# ошибка — username занят
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"hse.student","password":"hse.pass456"}'
# 400 {"detail":"Username taken"}

# ошибка — слишком короткие поля
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"","password":""}'
# 422 {"detail":[{"msg":"String should have at least 3 characters",...}]}
```

### POST /login

```bash
# успех
curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"hse.student","password":"hse.pass123"}'
# {"access_token":"eyJ...","token_type":"bearer"}

# неверный пароль
curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"hse.student","password":"hse.wrongpass"}'
# 401 {"detail":"Bad credentials"}

# пользователь не существует
curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"hse.ghost","password":"hse.pass123"}'
# 401 {"detail":"Bad credentials"}
```

## links.py

### POST /links/shorten

```bash
# анонимно, автогенерация кода
curl -s -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url":"https://hse.test/shorten"}'
# {"short_code":"4ary6W","original_url":"https://hse.test/shorten","created_at":"...","expires_at":null,"project":null,"clicks_count":0}

# с токеном, кастомный алиас + дата истечения
curl -s -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"original_url":"https://hse.test/promo","custom_alias":"hse-promo","expires_at":"2026-12-31T23:59:59","project":"hse-marketing"}'
# {"short_code":"hse-promo","original_url":"https://hse.test/promo",...}

# ошибка — алиас занят
curl -s -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url":"https://hse.test/other","custom_alias":"hse-promo"}'
# 400 {"detail":"Alias taken"}

# граничный — expires_at в прошлом (ссылка создастся, но при переходе вернёт 410)
curl -s -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url":"https://hse.test/expired-demo","expires_at":"2020-01-01T00:00:00"}'
# {"short_code":"eOTa2C","expires_at":"2020-01-01T00:00:00",...}
```

### GET /links/{short_code}

Редирект 307. Счётчик кликов увеличивается фоново.

```bash
# успех — редирект
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/links/4ary6W
# 307

# не найден
curl -s http://localhost:8000/links/hse-unknown
# 404 {"detail":"Not found"}

# истекла
curl -s http://localhost:8000/links/eOTa2C
# 410 {"detail":"Expired"}

# граничный — повторный запрос к истёкшей (отдаёт Redis, в БД не ходит)
curl -s http://localhost:8000/links/eOTa2C
# 410 {"detail":"Expired"}
```

### GET /links/{short_code}/stats

```bash
# успех
curl -s http://localhost:8000/links/4ary6W/stats
# {"original_url":"https://hse.test/shorten","created_at":"...","clicks_count":1,"last_used_at":"..."}

# не найден
curl -s http://localhost:8000/links/hse-none/stats
# 404 {"detail":"Not found"}

# граничный — ни одного перехода (clicks_count=0, last_used_at=null)
curl -s http://localhost:8000/links/hse-promo/stats
# {"original_url":"https://hse.test/promo","created_at":"...","clicks_count":0,"last_used_at":null}
```

### GET /links/search?original_url=

```bash
# найден
curl -s "http://localhost:8000/links/search?original_url=https://hse.test/shorten"
# [{"short_code":"4ary6W","original_url":"https://hse.test/shorten"}]

# не найден. пустой массив, не ошибка
curl -s "http://localhost:8000/links/search?original_url=https://hse.test/nonexistent"
# []

# граничный — один URL сокращён дважды
# [{"short_code":"4ary6W",...},{"short_code":"hse-alt",...}]
```

### GET /links/expired

```bash
# есть истёкшие
curl -s http://localhost:8000/links/expired
# [{"short_code":"eOTa2C","original_url":"https://hse.test/expired-demo","expires_at":"2020-01-01T00:00:00","clicks_count":0}]

# нет истёкших
# []
```

### PUT /links/{short_code}

Только владелец. Сбрасывает кеш в Redis.

```bash
# успех
curl -s -X PUT http://localhost:8000/links/hse-owned \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"new_original_url":"https://hse.test/update"}'
# {"message":"Updated"}

# нет токена
curl -s -X PUT http://localhost:8000/links/hse-owned \
  -H "Content-Type: application/json" \
  -d '{"new_original_url":"https://hse.test/update"}'
# 401 {"detail":"Missing token"}

# чужая ссылка
curl -s -X PUT http://localhost:8000/links/hse-owned \
  -H "Authorization: Bearer <token_of_hse.teacher>" \
  -H "Content-Type: application/json" \
  -d '{"new_original_url":"https://hse.test/evil"}'
# 403 {"detail":"Forbidden"}

# не найдена
curl -s -X PUT http://localhost:8000/links/hse-none \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"new_original_url":"https://hse.test/update"}'
# 404 {"detail":"Not found"}

# граничный — анонимная ссылка (user_id=NULL 403 для любого токена)
curl -s -X PUT http://localhost:8000/links/4ary6W \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"new_original_url":"https://hse.test/update"}'
# 403 {"detail":"Forbidden"}
```

### DELETE /links/{short_code}

```bash
# успех
curl -s -X DELETE http://localhost:8000/links/hse-owned \
  -H "Authorization: Bearer <token>"
# {"message":"Deleted"}

# нет токена — 401 {"detail":"Missing token"}
# чужая ссылка — 403 {"detail":"Forbidden"}
# не найдена — 404 {"detail":"Not found"}
```

### GET /projects/{project}/links

```bash
# есть ссылки
curl -s http://localhost:8000/projects/hse-marketing/links
# {"project":"hse-marketing","links":[{"short_code":"hse-promo","original_url":"https://hse.test/promo"}]}

# проект не существует — пустой список, не ошибка
curl -s http://localhost:8000/projects/hse-unknown/links
# {"project":"hse-unknown","links":[]}
```

### DELETE /secret/unused/cleanup?days=

Удаляет ссылки без переходов дольше `days` дней (default: 30).

```bash
# default 30 дней
curl -s -X DELETE http://localhost:8000/secret/unused/cleanup
# {"deleted":2}

# свой период
curl -s -X DELETE "http://localhost:8000/secret/unused/cleanup?days=7"
# {"deleted":5}

# нет подходящих
# {"deleted":0}

# days=0 — удалит всё без недавних переходов
curl -s -X DELETE "http://localhost:8000/secret/unused/cleanup?days=0"
```