# URL Shortener API

> Сгенерировано ИИ

Сервис для сокращения URL с аналитикой переходов, кэшированием и JWT-аутентификацией.

## Стек

- **FastAPI** — веб-фреймворк
- **PostgreSQL** — основная база данных
- **Redis** — кэширование ссылок и статистики
- **SQLAlchemy 2.0** — ORM
- **Docker Compose** — оркестрация контейнеров

## Запуск

### 1. Клонировать репозиторий и перейти в папку проекта

```bash
git clone <repo-url>
cd Project_url_shortener
```

### 2. Создать `.env` файл на основе примера

```bash
cp .env.example .env
```

Заполнить обязательные поля:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=urlshortener
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=your_admin_password

SECRET_KEY=your_secret_key   # openssl rand -hex 32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
BASE_URL=http://localhost:8000
```

### 3. Запустить

```bash
docker compose up --build
```

После старта:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

Администратор создаётся автоматически из переменных `ADMIN_*` при первом запуске.

## API

### Аутентификация

| Метод | Путь | Описание | Доступ |
|-------|------|----------|--------|
| POST | `/api/auth/register` | Регистрация | Публичный |
| POST | `/api/auth/login` | Вход, получение JWT | Публичный |
| GET | `/api/auth/me` | Текущий пользователь | Авторизован |

### Ссылки

| Метод | Путь | Описание | Доступ |
|-------|------|----------|--------|
| POST | `/api/links/shorten` | Создать короткую ссылку | Публичный / Авторизован |
| GET | `/{short_code}` | Редирект на оригинальный URL | Публичный |
| GET | `/api/links/{short_code}` | Информация о ссылке | Публичный |
| GET | `/api/links/{short_code}/stats` | Статистика переходов | Публичный |
| GET | `/api/links/my-links` | Ссылки текущего пользователя | Авторизован |
| GET | `/api/links/search?original_url=` | Поиск по оригинальному URL | Публичный |
| GET | `/api/links/expired` | Истёкшие ссылки пользователя | Авторизован |
| PUT | `/api/links/{short_code}` | Обновить оригинальный URL | Владелец / Админ |
| DELETE | `/api/links/{short_code}` | Удалить ссылку | Владелец / Админ |
| DELETE | `/api/links/cleanup-inactive` | Удалить неактивные ссылки | Только Админ |

## Примеры запросов

### Регистрация

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret123"}'
```

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-03-14T17:00:00Z"
}
```

### Вход

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -F "username=alice" \
  -F "password=secret123"
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Создание короткой ссылки

```bash
curl -X POST http://localhost:8000/api/links/shorten \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"original_url": "https://habr.com", "custom_alias": "habr"}'
```

```json
{
  "id": 1,
  "original_url": "https://habr.com",
  "short_code": "habr",
  "short_url": "http://localhost:8000/habr",
  "click_count": 0,
  "is_custom": true,
  "expires_at": "2026-04-14T17:00:00Z",
  "created_at": "2026-03-14T17:00:00Z"
}
```

### Редирект

```bash
curl -L http://localhost:8000/habr
# → 307 Redirect → https://habr.com
```

### Статистика

```bash
curl http://localhost:8000/api/links/habr/stats
```

```json
{
  "short_code": "habr",
  "original_url": "https://habr.com",
  "click_count": 42,
  "days_active": 7,
  "avg_clicks_per_day": 6.0,
  "last_accessed": "2026-03-14T18:00:00Z",
  "expires_at": "2026-04-14T17:00:00Z"
}
```

## База данных

### Таблица `users`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER | Первичный ключ |
| username | VARCHAR(50) | Уникальное имя пользователя |
| email | VARCHAR(255) | Уникальный email |
| hashed_password | VARCHAR(255) | Пароль, хешированный bcrypt |
| is_active | BOOLEAN | Активен ли пользователь |
| is_admin | BOOLEAN | Права администратора |
| created_at | TIMESTAMPTZ | Дата регистрации |

### Таблица `links`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER | Первичный ключ |
| original_url | TEXT | Оригинальный URL |
| short_code | VARCHAR(20) | Уникальный короткий код |
| user_id | INTEGER | Владелец (FK → users.id), nullable |
| is_custom | BOOLEAN | Задан пользователем или сгенерирован |
| click_count | INTEGER | Счётчик переходов |
| created_at | TIMESTAMPTZ | Дата создания |
| updated_at | TIMESTAMPTZ | Дата последнего обновления |
| last_accessed | TIMESTAMPTZ | Дата последнего перехода |
| expires_at | TIMESTAMPTZ | Срок действия (по умолчанию +30 дней) |

## Кэширование

Redis хранит три типа данных:

| Ключ | TTL | Содержимое |
|------|-----|------------|
| `link:{short_code}` | 1 час | JSON с данными ссылки |
| `stats:{short_code}` | 60 сек | JSON со статистикой |
| `popular_links` | без TTL | Sorted Set: код → количество переходов |

Кэш инвалидируется при каждом переходе, обновлении или удалении ссылки.
