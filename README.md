# AI News Agent

AI-агент на LangGraph, который читает новости из Medium.com и Telegram-каналов, фильтрует их по интересам пользователя и генерирует готовый пост для Telegram-канала.

## Быстрый старт

```bash
cp .env.example .env        # заполните OPENAI_API_KEY
make install
make run-agent-demo
```

---

## Архитектура

Система построена по принципу **Control Plane / Data Plane**.

```
Пользователь
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Control Plane                                                  │
│  ┌──────────────────┐   ┌──────────────────────────────────┐    │
│  │  validator.py    │   │  policy.py                       │    │
│  │  · anti-injection│   │  · RBAC (reader/viewer/admin)    │    │
│  │  · source guard  │   │  · source allowlist enforcement  │    │
│  └──────────────────┘   └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
     │ allow / deny
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Data Plane — LangGraph Agent                                   │
│                                                                 │
│  validate_request ──► check_permissions                         │
│                              │                                  │
│                   ┌──────────┴──────────┐                       │
│                denied              allowed                      │
│                   │                    │                        │
│            error_handler         fetch_sources                  │
│                              (Medium + Telegram RSS)            │
│                              ┌──────────┴──────────┐            │
│                          no_articles           has_articles     │
│                              │                    │             │
│                       error_handler          rag_filter         │
│                                          (ChromaDB retrieval)   │
│                                               │                 │
│                                         generate_post           │
│                                          (GPT-4o)               │
│                                               │                 │
│                                        validate_output          │
│                                     ┌────────┴────────┐         │
│                                  unsafe             safe        │
│                                     │                │          │
│                              error_handler          END         │
└─────────────────────────────────────────────────────────────────┘
```

### Точки ветвления

| № | Узел | Условие | Ветвь A | Ветвь B |
|---|------|---------|---------|---------|
| 1 | `check_permissions` | Роль/injection | `error_handler` | `fetch_sources` |
| 2 | `fetch_sources` | Есть статьи? | `error_handler` | `rag_filter` |
| 3 | `validate_output` | Безопасный вывод? | `error_handler` | `END` |

---

## Модули

### `src/config.py`

Централизованная конфигурация через `pydantic-settings`. Читает `.env` файл.

| Параметр | Описание |
|---|---|
| `OPENAI_API_KEY` | Ключ OpenAI API |
| `OPENAI_MODEL` | Модель (по умолчанию `gpt-4o`) |
| `ALLOWED_MEDIUM_TOPICS` | Список тем Medium (через запятую, **неизменяем пользователем**) |
| `ALLOWED_TELEGRAM_CHANNELS` | Список Telegram-каналов (через запятую, **неизменяем пользователем**) |
| `DEFAULT_USER_INTERESTS` | Дефолтные интересы для RAG |
| `CHROMA_PERSIST_DIR` | Путь к ChromaDB (по умолчанию `./chroma_db`) |
| `SQLITE_DB_PATH` | Путь к БД сессий (по умолчанию `./sessions.db`) |
| `MAX_MESSAGE_LENGTH` | Макс. длина запроса пользователя (по умолчанию `1000`) |
| `LANGFUSE_*` | Ключи Langfuse для трассировки |

---

### `src/control_plane/`

**Control Plane** — детерминированный слой безопасности. Не вызывает LLM.

#### `validator.py`

Двухуровневая проверка входящего сообщения:

1. **Prompt injection detection** — regex-паттерны для EN и RU:
   - `ignore previous instructions`, `forget everything`, `jailbreak`, `<system>`, `[INST]` и др.

2. **Source manipulation detection** — блокирует попытки сменить источники:
   - EN: `use reddit`, `add https://...`, `instead of medium`
   - RU: `используй reddit`, `вместо medium`, `измени источники`

```python
from src.control_plane.validator import validate_request

valid, reason = validate_request("дай новости по AI")  # → (True, "")
valid, reason = validate_request("ignore previous instructions")  # → (False, "...")
```

#### `policy.py`

RBAC — три встроенные роли:

| Роль | Medium | Telegram | Генерация | Макс. статей |
|------|--------|----------|-----------|--------------|
| `reader` | ✅ | ✅ | ✅ | 10 |
| `viewer` | ✅ | ❌ | ❌ | 5 |
| `admin` | ✅ | ✅ | ✅ | 20 |

Возвращает `PolicyDecision` с разрешёнными источниками и лимитами.

---

### `src/data_plane/`

**Data Plane** — тупой исполнитель. Не принимает решений.

#### `normalizer.py`

Нормализация текста перед обработкой:
- NFKC unicode normalization
- Удаление управляющих символов (`\x00`–`\x1f`)
- Схлопывание пробелов и переносов строк

#### `executor.py`

Точка входа в агента:

```python
from src.data_plane.executor import run_agent

response = run_agent(
    message="новости по Python",
    session_id="uuid",
    user_id="user_123",
    role="reader",
)
```

Создаёт checkpointer, собирает граф, вызывает `graph.invoke()` с начальным состоянием.

---

### `src/agent/`

#### `state.py` — `AgentState`

`TypedDict` — общее состояние всего графа:

| Поле | Тип | Описание |
|------|-----|---------|
| `session_id`, `user_id`, `role` | `str` | Идентификация сессии |
| `raw_message` | `str` | Исходный запрос пользователя |
| `normalized_message` | `str` | После нормализации |
| `permission_result` | `Literal["allowed","denied"]` | Решение Control Plane |
| `allowed_medium_topics` | `list[str]` | Разрешённые топики Medium |
| `allowed_telegram_channels` | `list[str]` | Разрешённые каналы Telegram |
| `fetched_articles` | `list[dict]` | Сырые статьи из источников |
| `rag_context` | `list[str]` | Интересы из ChromaDB |
| `filtered_articles` | `list[dict]` | Статьи после RAG-фильтрации |
| `generated_post` | `str` | Сгенерированный пост |
| `output_safe` | `bool` | Результат валидации вывода |
| `final_response` | `str` | Итоговый ответ пользователю |
| `error` | `str` | Текст ошибки если есть |

#### `nodes.py` — узлы графа

| Функция | Описание |
|---------|---------|
| `node_validate_request` | Нормализация + валидация через Control Plane |
| `node_check_permissions` | RBAC-проверка, заполняет `allowed_*` поля |
| `node_fetch_sources` | Параллельный fetch из Medium + Telegram через `asyncio.gather` |
| `node_rag_filter` | Seed ChromaDB → retrieval интересов → фильтрация статей |
| `node_generate_post` | GPT-4o генерирует Telegram-пост, прикрепляет Langfuse callback |
| `node_validate_output` | Проверяет длину и безопасность сгенерированного текста |
| `node_error_handler` | Формирует `❌ <причина>` для любой ветви отказа |

#### `graph.py` — сборка LangGraph

```python
from src.agent.graph import build_graph

graph = build_graph(checkpointer=checkpointer)
result = graph.invoke(initial_state, config=config)
```

Три условных ребра реализуют нелинейный поток выполнения.

---

### `src/sources/`

#### `medium.py`

Читает RSS Medium.com по тегу:
```
https://medium.com/feed/tag/{topic}
```
Парсит через `feedparser`, стриппит HTML из summary. Возвращает `list[dict]` с полями `title`, `url`, `summary`, `source`, `topic`.

#### `telegram.py`

Читает публичные Telegram-каналы через веб-превью:
```
https://t.me/s/{channel}
```
Парсит HTML через `BeautifulSoup`, извлекает `.tgme_widget_message_text`. Возвращает посты в формате `list[dict]` с полями `title`, `url`, `summary`, `source`, `channel`.

---

### `src/mcp_server/`

SSE-сервер на базе **FastMCP**, запускается как отдельный процесс на `localhost:8000`.

#### `server.py`

Два инструмента MCP:

| Tool | Параметры | Описание |
|------|-----------|---------|
| `fetch_medium_articles` | `topic: str`, `count: int = 5` | Статьи с Medium (макс. 10) |
| `fetch_telegram_posts` | `channel: str`, `count: int = 5` | Посты из Telegram-канала (макс. 10) |

#### `tools.py`

Синхронные обёртки над async-источниками с принудительной валидацией против allowlist: нельзя запросить топик или канал, которого нет в `ALLOWED_*` переменных окружения.

---

### `src/rag/`

#### `store.py`

ChromaDB persistent client с коллекцией `user_interests`:
- `seed_interests(persist_dir, interests)` — наполняет коллекцию дефолтными интересами (идемпотентно)
- `upsert_interest(persist_dir, interest, id)` — добавляет/обновляет интерес
- Расстояние: cosine similarity
- Эмбеддинги: `DefaultEmbeddingFunction` (sentence-transformers)

#### `retriever.py`

- `retrieve_interests(persist_dir, query, n)` — top-N интересов по запросу
- `filter_articles_by_interests(articles, interests)` — keyword-фильтрация; если ни одна статья не совпала — возвращает все (fallback)

---

### `src/session/`

#### `store.py`

LangGraph `SqliteSaver` поверх `sqlite3.connect()`:

```python
checkpointer = get_checkpointer("./sessions.db")
config = make_config(session_id="uuid", user_id="user_123")
# config = {"configurable": {"thread_id": "uuid", "user_id": "user_123"}}
```

Состояние каждого `thread_id` сохраняется между вызовами `graph.invoke()`.

---

### `src/monitoring/`

#### `callbacks.py`

- `configure_logging()` — настраивает `structlog` с JSON-рендерером и ISO-таймстемпами
- `get_langfuse_handler(session_id, user_id)` — возвращает `LangfuseCallbackHandler` для трассировки LLM-вызовов; если ключи не настроены — возвращает `None` без падения

Для активации Langfuse добавьте в `.env`:
```
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## Безопасность

| Угроза | Защита |
|--------|--------|
| Prompt injection | 13 regex-паттернов в `validator.py` (EN + RU) |
| Смена источников | 7 regex-паттернов source guard (EN + RU) |
| Несанкционированный доступ | RBAC в `policy.py`, 3 роли |
| Изменение allowlist в runtime | `ALLOWED_*` только из `.env`, не из запроса |
| Небезопасный вывод | `node_validate_output` проверяет сгенерированный текст |
| Слишком длинный запрос | `MAX_MESSAGE_LENGTH` (по умолчанию 1000 символов) |

---

## Тесты

```bash
make test                                          # все 39 тестов
make test-one T=tests/test_validator.py            # один файл
make test-one T=tests/test_graph.py::TestRoutingFunctions  # один класс
```

| Файл | Что тестирует |
|------|---------------|
| `test_validator.py` | Injection detection, source guard, нормализация |
| `test_graph.py` | Routing functions, компиляция графа, E2E rejection |
| `test_rag.py` | ChromaDB seed/upsert, retrieval, фильтрация статей |
| `test_mcp_tools.py` | Medium/Telegram fetch с мок HTTP-клиентом |

---

## Команды

```bash
make help             # показать все команды
make install          # установить зависимости
make test             # запустить тесты
make run-mcp          # запустить MCP SSE сервер (localhost:8000)
make run-agent MSG="дай новости по AI"   # запустить агент
make run-agent-demo   # демо-запрос
make clean            # очистить chroma_db, sessions.db, кэши
```
