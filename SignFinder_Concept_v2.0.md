# Концепция SignFinder

## Система автоматического поиска мест подписи и подписания договоров PDF/DOCX

---

## История версий

| Версия | Дата | Что изменилось |
|--------|------|----------------|
| v1.0 | 05.05.2026 | Первый прототип: regex-поиск, Streamlit монолит, GCP Cloud Run, parties.json |
| v1.1 | 06.05.2026 | pipelineAuto1: LLM-extraction нашей стороны, генерация regex под документ |
| v1.2 | 07.05.2026 | Светофор (green/yellow) и реестр шаблонов — концепция и первая реализация |
| v1.3 | 08.05.2026 | Streamlit CRUD, LibreOffice DOCX→PDF, LLM-валидация, промокод-авторизация |
| v1.4 | 10.05.2026 | Концепция API-слоя: FastAPI, signfinder-core как pip-пакет, storage abstraction |
| v1.5 | 12.05.2026 | Реструктуризация roadmap: IMAP single-user, мульти-LLM в план, мобайл → идеи |
| v1.6 | 14.05.2026 | Anchor-based templates: TextAnchor вместо bbox-координат |
| v1.7 | 16.05.2026 | Ручная доразметка кликом, drag якорей, сохранение шаблонов |
| v1.8 | 19.05.2026 | Fingerprint matching (simhash+jaccard+cosine), светофор в продакшене |
| **v1.9** | **21.05.2026** | **FastAPI signfinder-api + docker-compose + LocalFilesystemStorage** |
| **v1.10** | **24.05.2026** | **Мульти-LLM (Anthropic + OpenAI + DeepSeek + Gemini), конфиг через UI** |
| **v1.11** | **26.05.2026** | **PNG-подпись вместо красных рамок, /v1/analyze endpoint** |
| **v1.12** | **28.05.2026** | **Пакетная обработка UI (Пакет / Разбор / Тестирование-заглушка)** |
| **v1.13** | **30.05.2026** | **Предобработка подписи (OpenCV), dedup якорей 3-шаг, x-offset 20pt** |
| **v1.14** | **31.05.2026** | **Маркер места подписи (4×12мм), Тестирование в Настройках** |
| **v2.0** | **31.05.2026** | **Актуализация концепции, тестирование, multi-LLM промпты** |

---

## 1. Резюме концепции

SignFinder автоматизирует **процесс подписания договоров**: находит где, кому и в каком порядке ставить подпись — тот шаг который DocuSign, Adobe Sign и все остальные оставляют человеку.

**Целевая аудитория:** delivery-менеджеры, юристы среднего звена, операционисты — все кто обрабатывает 10–200 договоров в месяц без enterprise-CLM.

**Ключевая метрика:** доля документов прошедших полный цикл «загрузил → нашлись места → подписано → скачано» без ручных правок. Цель MVP — 70%, продакшен — 90%+.

**Экономика:** многоуровневая обработка с оптимизацией стоимости токенов.

| Уровень | Метод | Стоимость | Доля документов |
|---------|-------|-----------|----------------|
| 0 | Fingerprint matching (шаблон уже есть) | ~$0 | 50%+ после накопления шаблонов |
| 1 | Regex по parties.json | ~$0 | 30% |
| 2 | LLM-валидация regex-кандидатов | $0.01–0.02 | 15% |
| 3 | LLM-first fallback | $0.05–0.10 | 5% |
| 4 | Ручная разметка → сохранить шаблон | трудозатраты оператора | <1% |

---

## 2. Текущее состояние (v1.14)

### 2.1 Реализовано и работает

| Функция | Реализация | Версия |
|---------|-----------|--------|
| Загрузка PDF/DOCX до 50 МБ | PyMuPDF + LibreOffice headless | v1.0 |
| Авто-детект языка (ru/en/pl) | langdetect | v1.0 |
| Реестр сторон с regex-паттернами | parties.json, LocalFilesystemStorage | v1.0 |
| Поиск мест подписи по regex | Паттерны из parties.json по языку | v1.0 |
| Текстовые якоря (anchor-based templates) | TextAnchor: text + bbox + page_hint | v1.7 |
| Ручная доразметка кликом | streamlit-image-coordinates | v1.7 |
| LLM-валидация мест подписи | Опционально, через LLMClient | v1.7 |
| Fingerprint матчинг | simhash + jaccard + cosine + page_count | v1.8 |
| Светофор green/yellow/red | Пороги 0.85 / no_match | v1.8 |
| Сохранение и применение шаблонов | CRUD через API | v1.8 |
| signfinder-core pip-пакет | GitHub: alexgeorg2507-creator/signfinder-core | v1.9 |
| FastAPI signfinder-api | REST API поверх core, v1.14.0 | v1.9 |
| docker-compose деплой | api:8000 + streamlit:8501 | v1.9 |
| LocalFilesystemStorage | Volumes в Docker | v1.9 |
| Мульти-LLM backend | Anthropic, OpenAI, DeepSeek, Gemini | v1.10 |
| Настройка LLM через UI | llm_config.json, страница Настройки → LLM | v1.10 |
| PNG-подпись в превью | Вместо красных рамок, overlay-совместимый размер | v1.11 |
| Пакетная обработка (Пакет) | Загрузка до 100 файлов, сводная таблица, drill-down | v1.12 |
| Вкладка «Разбор» жёлтых | Очередь из пакета, PDF с PNG-подписями, исходы | v1.12 |
| Предобработка подписи | OpenCV: crop, HSV+adaptive, RGBA, 600px max | v1.13 |
| Dedup якорей 3-шаговый | Exact bbox → semantic text → underscore priority | v1.13 |
| Горизонтальный сдвиг подписи | SIGNATURE_X_OFFSET_PT=20 (~7мм) от подчёркивания | v1.13 |
| Маркер места подписи | 4×12мм прямоугольник на правом поле | v1.14 |
| Настройки режима простановки | use_signature + use_marker + marker_color | v1.14 |
| Тестирование в Настройках | Вкладка в странице Настройки | v1.14 |

### 2.2 Известные ограничения (актуальные)

| Ограничение | Влияние | План |
|-------------|---------|------|
| Нет поддержки сканов | OCR отсутствует | Out of scope MVP, Document AI в v2.x |
| «По подписанту» с hardcoded именами | parties.json паттерны не матчат динамически введённые имена | Tech debt, v1.15+ |
| Ключи LLM в открытом JSON | Только для локального Docker, не для облака | Шифрование при выходе в prod |
| Один подписант (signer_id="default") | Нет multi-signer | v2.x |
| dedup логика в Streamlit, не в core | Дублирование при других клиентах | Tech debt, переезд в core |
| sf.sign() не принимает signer_id явно | Обходится через storage path | Tech debt |
| Нет автоматических тестов | Регрессии ловятся глазами | v1.15 — автотесты |
| Синтетический паттерн подписи захардкожен в auto1.py | Не учитывает язык, одна форма `(ФИО)` | TD-07, вынести в markers-конфиг |

### 2.3 Архитектура деплоя

```
C:\work\
├── .dockerignore                   ← контекст сборки C:\work\
├── signfinder-core\                ← pip-пакет v1.14.0
├── signfinder-api\                 ← FastAPI app (единственная точка истины)
└── SignPDFMVPLocal\
    ├── api\Dockerfile              ← COPY signfinder-api/app/
    ├── streamlit\                  ← Streamlit UI
    ├── data\api\                   ← volumes (шаблоны, конфиги, подпись)
    └── docker-compose.yml

Cloud (GCP):
    Cloud Run: signfinder-api
    GCS: gs://signfinder-config/ (шаблоны, конфиги)
```

---

## 3. Позиционирование на рынке

### 3.1 Прямые конкуренты

| Продукт | Что делает | Чего нет |
|---------|-----------|----------|
| DocuSign | Ручное перетаскивание полей подписи | Авто-поиск мест в чужих документах |
| Adobe Sign | То же, шаблоны для своих документов | Интеллектуальный поиск в загружаемых |
| HelloSign / Dropbox Sign | API + ручная разметка | Нет автопоиска |
| PandaDoc | Создание + подписание шаблонов | Авто-поиск только в собственных шаблонах |

### 3.2 Косвенные конкуренты

| Продукт | Фокус | Почему не конкурент |
|---------|-------|---------------------|
| Kira / Luminance | Анализ уже подписанных документов | Другой процесс |
| LawGeex | Review vs корпоративных политик | Не занимается подписанием |
| Ironclad CLM | Полный жизненный цикл договора | Enterprise, другой ценовой сегмент |
| Harvey AI / Spellbook | LLM-копилот для юристов | Нет процессного подписания |

**Вывод:** SignFinder — единственный продукт автоматизирующий поиск мест подписи в **чужих загружаемых документах** без enterprise-веса.

### 3.3 Позиционирование

| Параметр | Позиция |
|----------|---------|
| Сегмент | Mid-market, 10–200 договоров/месяц |
| Стоимость обработки | $0.01–0.10 на документ |
| Языки | ru, en, pl |
| Юрисдикции | РФ/ЕАЭС, EU (Польша приоритет) |
| Отличие | Единственный продукт с авто-поиском в чужих документах |

---

## 4. Архитектура многоуровневой обработки

### 4.1 Каскад уровней

```
Документ загружен
        ↓
┌─────────────────────────────┐
│ Уровень 0: Fingerprint      │
│ simhash + jaccard + cosine  │
│ + page_count → score ≥ 0.85 │
└──────────────┬──────────────┘
      нет      │   да → применить шаблон → 🟢 green
               ↓
┌─────────────────────────────┐
│ Уровень 1: Regex            │
│ parties.json по языку       │
└──────────────┬──────────────┘
      нет      │   найдено → LLM-валидация → 🟡/🟢
               ↓
┌─────────────────────────────┐
│ Уровень 2: LLM-fallback     │
│ pipelineAuto1               │
│ extraction → regex gen      │
│ → validation                │
└──────────────┬──────────────┘
      нет      │   найдено → 🟡 yellow (требует оператора)
               ↓
┌─────────────────────────────┐
│ Уровень 3: Ручная разметка  │
│ Оператор кликает по PDF     │
│ → создаётся якорь           │
│ → опционально шаблон        │
└─────────────────────────────┘
```

### 4.2 Светофор — определения

| Цвет | API `traffic_light` | Когда | Действие |
|------|---------------------|-------|---------|
| 🟢 | `green` | Score ≥ 0.85, шаблон применён уверенно | Подпись расставлена автоматически |
| 🟡 | `yellow` | Зоны найдены (LLM или слабый шаблон), нет уверенности | Подпись расставлена + рекомендована проверка оператором |
| 🔴 | `no_match` | Технический сбой: битый PDF, fitz упал, исключение матчера | Failed/ с объяснением причины |

**Важно:** `no_match` — только технический сбой. «LLM ничего не нашёл» или «нет шаблонов» = `yellow`.

---

## 5. Пайплайн анализа (pipelineAuto1)

### 5.1 Шаги

| Шаг | Что | Где в коде |
|-----|-----|-----------|
| 0 | Парсинг PDF/DOCX, детекция языка | `signfinder/pdf/parser.py` |
| 1 | Поиск заголовка (титульник vs преамбула) | `signfinder/pipeline/auto1.py` |
| 2 | LLM-extraction нашей стороны | `signfinder/prompts/extraction.py` |
| 3 | Генерация regex под этот документ | `signfinder/prompts/regex_generation.py` |
| 4 | Поиск мест подписи по regex + smart bbox | `signfinder/pipeline/pattern_extractor.py` |
| 5 | LLM-валидация (опционально) | `signfinder/prompts/validation.py` |
| 6 | Возврат якорей | `AnalysisResponse` |

### 5.2 Промпты пайплайна

5 промптов: `extraction`, `regex_generation`, `validation`, `party_resolver`, `settings`.

**Ключевое решение:** промпты **универсальные** — один текст для всех 4 LLM-провайдеров. Различия провайдеров изолированы в JSON-механике (`complete_structured()`) и не требуют отдельных текстов. Подробнее — в документе `MULTILLM_PROMPTS_DECISION.md`.

Проверка гипотезы — через автотесты v1.15: эталонный корпус × 4 провайдера, если провайдер проседает по метрикам — тогда точечный `provider_hint`, не отдельный промпт.

### 5.2.1 Принцип: стабильная конвенция vs специфика документа

Ключевое архитектурное различие при работе с LLM в пайплайне:

| Что | Где обрабатывается | Лекало |
|-----|-------------------|--------|
| Стабильная конвенция (`____ (ФИО)`, `Заказчик ___`) | Детерминированный конфиг по языкам (Слой 1-2) | markers, parties.json |
| Специфика документа (наша сторона, юрлицо, роли) | LLM + промпт (Слой 3) | extraction, regex_generation |

**Антипаттерн:** просить LLM регенерить стабильную структурную конвенцию каждый
прогон. Это хрупко на ЛЮБОЙ модели (Claude сгенерил, DeepSeek — нет; обе стохастичны).
Структурные конвенции переносятся в детерминированный слой — это улучшает всех
провайдеров одновременно. «Особенность модели лечить промптом» верно только для
специфики документа, не для конвенций.

Текущее нарушение принципа — TD-07 (синтетический паттерн в auto1.py), подлежит
переносу в markers-конфиг.

### 5.3 Хранение данных

| Сущность | Где | Формат |
|----------|-----|--------|
| Шаблоны | `data/api/templates/` | JSON по одному на шаблон |
| Стороны (parties) | `data/api/parties.json` | JSON массив с паттернами |
| Профиль подписанта | `data/api/signer_profile.json` | JSON |
| PNG подписи | `data/api/signers/default/signature.png` | PNG RGBA |
| LLM config | `data/api/llm_config.json` | JSON с ключами |
| Настройки светофора | `data/api/settings/traffic_light.json` | JSON |
| Настройки маркера | `data/api/settings/sign_mode.json` | JSON |
| Маркеры подписи | `data/api/settings/markers.json` | JSON по языкам |

---

## 6. Fingerprint и матчинг шаблонов

### 6.1 Алгоритм fingerprint

Четыре компоненты, взвешенная сумма:

| Компонента | Алгоритм | Вес |
|-----------|----------|-----|
| simhash | 64-bit simhash заголовка документа | 0.40 |
| jaccard | Jaccard similarity множеств слов | 0.30 |
| cosine | Cosine similarity TF-IDF векторов | 0.20 |
| page_count | Совпадение количества страниц | 0.10 |

**Порог green:** score ≥ 0.85  
**Порог perfect:** score ≥ 0.99 (выше — не триггерит логику коллизии)

### 6.2 Приоритет кандидатов в green-зоне (0.85–0.99)

Сортировка по `created_at DESC` — побеждает самый свежий откорректированный шаблон, а не самый высокоскорированный старый.

### 6.3 Ретенция шаблонов

Политика ретенции (настраиваемая в Настройках):
- 30+ дней без применения → статус `archived`
- 90+ дней в `archived` → удаление с бэкапом
- `times_rejected / times_applied > 0.5` → `low_quality`

---

## 7. API-слой

### 7.1 Архитектура

```
До v1.9:
Streamlit → core/*.py → GCS/LocalFS, LLM API

С v1.9:
Streamlit → HTTP → signfinder-api → signfinder-core → LocalFS/GCS, LLM API
               ↑
    Mobile, MCP, integrations (будущее)
```

**signfinder-core** — pip-пакет, единственный источник бизнес-логики. Не зависит от FastAPI, Streamlit, GCP.

**signfinder-api** — тонкая FastAPI-обёртка. Все изменения только в `signfinder-api/app/` (единственная точка истины).

**Stateless** — PDF не хранится между запросами. Подписанный PDF возвращается в response body.

### 7.2 Endpoints (реализованы в v1.14)

**Pipeline:**
```
POST /v1/analyze              PDF → AnalysisResponse (светофор, anchors, fingerprint)
POST /v1/analyze/batch        Пакет PDF (до 100) → BatchAnalysisResponse
POST /v1/sign                 PDF + anchors_json + signer_id → подписанный PDF
POST /v1/anchor/from-click    PDF + page/x/y → TextAnchor
POST /v1/preview              PDF + page → PNG превью
```

**Templates:**
```
GET/POST /v1/templates
GET/PATCH/DELETE /v1/templates/{id}
GET /v1/templates/search
POST /v1/templates/{id}/apply
```

**Signers:**
```
GET/PUT /v1/signers/{id}
GET/PUT /v1/signers/{id}/signature
POST /v1/signers/{id}/signature/process   ← v1.13: предобработка OpenCV
```

**Settings:**
```
GET/PUT /v1/settings/traffic-light
GET/PUT /v1/settings/markers
GET/PUT /v1/settings/retention
GET/PUT /v1/settings/sign-mode            ← v1.14: use_signature, use_marker
```

**LLM Config:**
```
GET/POST /v1/config/llm
POST /v1/config/llm/test
```

**Parties, Audit, Jobs** — согласно документации `/docs`.

### 7.3 StorageBackend — допустимые методы

```python
sf.storage.read_bytes(path)  → Optional[bytes]
sf.storage.write_bytes(path, data)
sf.storage.read_json(path)   → Optional[dict]
sf.storage.write_json(path, data)
sf.storage.exists(path)      → bool
sf.storage.delete(path)      → bool
sf.storage.list_prefix(prefix) → list[str]
```

**НЕ существует:** `.read()`, `.write()`, `.get()`, `.put()`. Написание несуществующего метода не падает при импорте — только в рантайме.

---

## 8. Multi-LLM backend

### 8.1 Архитектура

| Слой | Файл | Что делает |
|------|------|-----------|
| Абстракция | `signfinder/llm/base.py` | `LLMClient.complete_structured()` |
| Anthropic | `anthropic_client.py` | Текущая реализация |
| OpenAI | `openai_client.py` | function calling для JSON |
| DeepSeek | `deepseek_client.py` | response_format для JSON |
| Gemini | `gemini_client.py` | response_mime_type |
| Factory | `factory.py` | Читает llm_config.json, fallback на env |
| Config | `config.py` | Читалка/писалка llm_config.json |

### 8.2 Конфигурация

```json
{
  "active_provider": "anthropic",
  "providers": {
    "anthropic": {"api_key": "sk-ant-..."},
    "openai":    {"api_key": "sk-..."},
    "deepseek":  {"api_key": ""},
    "gemini":    {"api_key": ""}
  }
}
```

Пустой ключ = провайдер не настроен. Приоритет: `llm_config.json → env var → RuntimeError`.

### 8.3 Решение по промптам (зафиксировано)

Промпты универсальные. Не плодить 5 промптов × 4 провайдера = 20 текстов. Проверка через автотесты (v1.15). Точечные оверрайды только по данным измерений. Полное обоснование — `MULTILLM_PROMPTS_DECISION.md`.

---

## 9. Подпись — обработка и наложение

### 9.1 Предобработка подписи (v1.13)

`POST /v1/signers/{id}/signature/process`:
1. PNG/JPG/GIF → RGBA (Pillow)
2. Двойная детекция чернил: HSV-маска (чёрный + синий) + adaptive threshold
3. Морфологическая очистка (OpenCV)
4. Bounding box чернил, padding 12px
5. Валидация: ink_coverage, bbox_aspect, размер относительно листа → confidence + warnings
6. Crop + прозрачный фон (alpha mask с gaussian blur)
7. Downscale до 600px ширины максимум (LANCZOS, без растяжения)
8. Возврат: `{processed_png_b64, confidence, warnings, output_size, ink_coverage}`

Endpoint не сохраняет. Сохранение — отдельный `PUT /signature` с processed PNG.

### 9.2 Наложение подписи (overlay.py)

Параметры `apply_signature()`:
- `scale` — масштаб высоты (1.0 = 42pt ≈ 15мм)
- `use_signature` — накладывать PNG (default True)
- `use_marker` — ставить маркер места (default False)
- `marker_color` — "pink" или "gray"

**Маркер места подписи** — прямоугольник 11.3pt × 34pt (4×12мм) на правом поле страницы:
```
x0 = page_width - 14pt
x1 = page_width - 3pt
y_center = (anchor_bbox[1] + anchor_bbox[3]) / 2
```
Розовый: (1.0, 0.714, 0.757). Серый: (0.706, 0.706, 0.706). Отрисовка через `page.draw_rect()`.

**Позиционирование подписи:** выравнивание по подчёркиванию + SIGNATURE_X_OFFSET_PT=20 (~7мм) сдвиг вправо.

---

## 10. Пакетная обработка

### 10.1 Три вкладки

**«Пакет»** — загрузка до 100 файлов (PDF + DOCX), прогресс, таблица с светофором/шаблоном/score/зонами/временем. Drill-down: simhash/jaccard/cosine/page_count + якоря. Кнопка «В разбор» для жёлтых.

**«Разбор»** — очередь жёлтых из пакета. PDF с PNG-подписями. Исходы: Подтвердить / Переподписать / Сохранить как шаблон / Отклонить.

**«Тестирование»** — v1.15, пока заглушка.

### 10.2 DOCX в пакете

DOCX конвертируется в PDF через `parse_document()` (LibreOffice) в Streamlit **до** отправки в API. LibreOffice есть только в Streamlit контейнере. API получает только PDF. Это обеспечивает идентичный fingerprint с авто-подписанием.

---

## 11. Тестирование — стратегия и KPI

### 11.1 Ключевая развилка

Система из двух миров:
- **Детерминированный код** — fingerprint, matching, dedup, overlay. Обычный pytest, CI на каждый коммит.
- **LLM-пайплайн** — extraction, regex, валидация. Corpus-based eval с метриками, запускается по требованию.

Смешивать их — ошибка. Это две разные машины.

### 11.2 Пирамида тестов

**Уровень 1: Unit-тесты детерминированного ядра (делать первым)**

Покрыть места которые уже ломались:

| Модуль | Что тестировать | Почему |
|--------|----------------|--------|
| `fingerprint/` | simhash parse (decimal-first, 64-bit), jaccard, cosine, page_count | Был баг hex/decimal |
| `templates/matcher.py` | пороги green/yellow, коллизия на 0.99, сортировка by created_at DESC | Был баг трёх score=1.0 |
| `_dedup_anchors` | 3-шаговый dedup на синтетических наборах | Был баг с 42 якорями |
| `pdf/overlay.py` | `_find_underscore_anchor`, sig_rect, маркер, x-offset | Был баг масштаба |
| `signature/processor.py` | crop bbox, ink_coverage, валидация (детерминированные части) | Новая логика |
| `storage/local.py` | read_bytes/write_bytes/exists roundtrip | Был баг read() vs read_bytes() |

**Уровень 2: Integration — API с мок-LLM**

Каждый endpoint с замоканным LLMClient. Тестируем проводку, не модель.
Ловит: auth, 404, 422, storage-баги (баг `read()` vs `read_bytes()` поймался бы здесь).

**Уровень 3: Contract-тесты LLM-клиентов**

4 клиента: на известный промпт → валидный JSON, `complete_structured()` парсит.
Записанные ответы (VCR-style) — не жечь API в CI.

**Уровень 4: Eval-тесты на корпусе (это KPI)**

Прогон полного пайплайна на эталонном корпусе. По требованию, не в каждом коммите. **Здесь проверяется решение об универсальных промптах.**

**Уровень 5: E2E**

Документ → analyze → sign → PDF валиден, есть image XObject, маркер на месте.

### 11.3 Структура тестового корпуса

Каждый документ в корпусе с ожидаемым результатом:

```json
{
  "filename": "arenda_001.pdf",
  "expected_template": "Аренда_v3",
  "expected_traffic_light": "green",
  "expected_signature_count": 2,
  "expected_our_side": {"legal_entity": "...", "signer": "..."}
}
```

### 11.4 Сценарии (обязательное покрытие)

| Сценарий | Ожидаем |
|----------|---------|
| Точное совпадение с шаблоном | green, правильный шаблон |
| Слабая вариация шаблона | green, score ниже |
| Два шаблона с близким score | yellow, коллизия |
| Неизвестный тип договора | yellow, LLM-fallback |
| Битый PDF | no_match (red) |
| DOCX на входе | конвертация → analyze |
| Подпись на последней странице | якорь на правой странице (page_hint) |
| Несколько мест подписи | N якорей, не дубли |
| Адресный блок (regex over-match) | 1–2 якоря, не 42 |
| en / pl документ | язык определён, обработан |

Отдельный мини-корпус для signature processor: чистый скан, фото с тенью, лист с одной подписью, синяя ручка, красная (должна быть confidence=0).

### 11.5 KPI-метрики (per-provider таблица)

| Метрика | Описание |
|---------|----------|
| Template accuracy | Выбран правильный шаблон (% корпуса) |
| Traffic light accuracy | Цвет совпал с ожидаемым |
| Anchor precision | Из поставленных якорей сколько верных |
| Anchor recall | Из реальных мест подписи сколько найдено |
| JSON validity rate | Доля валидного JSON с первой попытки |
| Latency p50/p95 | На провайдера, в мс |
| Cost per doc | Токены × цена |

**Таблица**: 4 провайдера × 7 метрик = здесь видно где нужен prompt override.

### 11.6 Приоритет разработки тестов

1. Unit на детерминированное ядро — быстро, ловит регрессии, CI на каждый коммит
2. Integration с мок-LLM — ловит storage-баги и проводку
3. Corpus + eval — KPI, сравнение провайдеров, валидация промптов
4. Contract и E2E — по остаточному принципу

### 11.7 Где хранить тесты

- Unit + integration: в `signfinder-core/tests/` рядом с кодом
- Эталонный корпус (реальные PDF): **отдельное хранилище** (не в git core — персональные данные в договорах)
- Eval-runner: скрипт или отдельный репозиторий `signfinder-tests/`

---

## 12. Roadmap

### 12.1 Текущий статус

| Версия | Что | Статус |
|--------|-----|--------|
| v1.9 | FastAPI + docker-compose | ✅ |
| v1.10 | Мульти-LLM | ✅ |
| v1.11 | PNG-подпись вместо рамок | ✅ |
| v1.12 | Пакетная обработка UI | ✅ |
| v1.13 | Предобработка подписи | ✅ |
| **v1.14** | **Маркер + Тестирование в Настройках** | 🔨 В работе |
| **v1.15** | **Автотесты + KPI-корпус** | ⏳ |
| **v1.16** | **IMAP-агент Docker (single-user)** | ⏳ |
| **v1.17** | **Pre-flight check R-01..R-07** | ⏳ |

**После v1.17 — MVP завершён.**

### 12.2 v1.15 — Автотесты + KPI

Unit-тесты детерминированного ядра + integration с мок-LLM + эталонный корпус для eval. Полная стратегия — в главе 11.

### 12.3 v1.16 — IMAP-агент (single-user Docker)

Фоновый агент в том же docker-compose стеке. Основной сценарий:

```
Inbox/SignFinder/ → analyze() → по светофору:
  green  → sign() → ответное письмо → Signed/
  yellow → RequiresReview/ (разбирает оператор в UI)
  red    → Failed/ (лог причины)
```

Структура папок IMAP:
```
Inbox/SignFinder/
├── (incoming)
├── Signed/
├── RequiresReview/
├── Failed/
└── Archive/
```

**Принципы:**
- Без облачных зависимостей — только ANTHROPIC_API_KEY наружу
- LLM API key клиента, не наш — биллинг напрямую
- STORAGE_MODE=local, конфиг через env vars
- Polling каждые N минут (default 5)

Протоколы: IMAP IDLE + polling fallback. Поддержка Exchange / Postfix / GSuite — по первому реальному клиенту.

### 12.4 v1.17 — Pre-flight check (правила целостности)

Второй светофор — проверка самого договора до подписания:

| Правило | Проверяет |
|---------|-----------|
| R-01 | Наличие реквизитов сторон |
| R-02 | Соответствие предмета договора |
| R-03 | Наличие обязательных разделов |
| R-04 | Срок действия |
| R-05 | Порядок расчётов |
| R-06 | Ответственность сторон |
| R-07 | Подписи и реквизиты в конце |

---

## 13. Идеи развития (после MVP)

Все идеи — **реактивные**: вводим только при подтверждённом бизнес-кейсе.

### Наиболее вероятные первые шаги после MVP

| Направление | Триггер | Срок |
|-------------|---------|------|
| MCP-сервер для Claude Desktop / Cursor | Запросы от разработчиков | 1–2 недели |
| Multi-tenant + сайт регистрации | Product-led growth, первые платящие | 12–16 недель |
| iOS приложение | Пользователи запрашивают мобайл | 6–8 недель |
| Sessions (двустороннее подписание) | Запрос на подписание контрагентом | 2–3 недели |

### Multi-LLM расширения

| Фича | Когда |
|------|-------|
| Автоматический fallback между провайдерами | После автотестов (v1.15) |
| Per-task выбор LLM (extraction → Claude, валидация → DeepSeek) | По данным cost analysis |
| Локальные LLM (Llama, Mistral) | Air-gapped клиенты с GPU |
| Google Document AI Contract Parser | Batch 1000+ документов или OCR |

### Enterprise

RBAC, multi-mailbox, SAML/OIDC SSO, compliance reports — по запросу конкретных клиентов.

---

## 14. Связанные документы

| Файл | Что |
|------|-----|
| `DEPLOY_CONSTRAINTS.md` | Правила деплоя, Docker, PowerShell, StorageBackend API |
| `MULTILLM_PROMPTS_DECISION.md` | Решение об универсальных промптах |
| `TECH_DEBT.md` | Технический долг (в signfinder-core) |
| `data/api/llm_config.json` | Активный LLM-провайдер и ключи |
| `data/api/settings/sign_mode.json` | Режим простановки подписи/маркера |
| API Swagger | `http://localhost:8000/docs` (локально) |

---

## Приложение A. Облачные сервисы парсинга (опции для v2.x+)

### A.1 Google Document AI

| Процессор | Применимость к SignFinder |
|-----------|--------------------------|
| Document OCR | Закрывает кейс сканов — out of scope MVP |
| Layout Parser | Разбор структуры разделов — кандидат v2.x |
| Contract Parser | Альтернатива LLM extraction, ~$30/1000 страниц |

**Стоимость:** OCR ~$1.50, Layout ~$10, Contract ~$30 за 1000 страниц.
**Рекомендация для MVP:** не нужен. Рассмотреть при batch 1000+ документов или при появлении сканов.

### A.2 AWS Textract

| Фича | Применимость |
|------|-------------|
| AnalyzeDocument TABLES | Сильнее Google в табличных кейсах |
| AnalyzeDocument SIGNATURES | **Детекция уже наложенных подписей** (уникально) |

**Минус:** мы на GCP — cross-cloud сложности. Резерв для специфичных кейсов.

### A.3 Azure Form Recognizer

Prebuilt Contract model — аналог Google Contract Parser. Актуален для Azure-клиентов.

### A.4 Сравнение

| Параметр | Google | AWS | Azure |
|----------|--------|-----|-------|
| Структура документа | ★★★ | ★★ | ★★ |
| Таблицы | ★★ | ★★★ | ★★ |
| Договоры | ★★★ | — | ★★ |
| Детекция подписей как объектов | — | ★★★ | — |
| Vendor lock для GCP-стека | Минимальный | Cross-cloud | Cross-cloud |

---

## Приложение B. Библиотеки и технологический стек

### B.1 signfinder-core

| Библиотека | Для чего | Версия |
|-----------|----------|--------|
| PyMuPDF (fitz) | PDF парсинг, рендеринг, overlay | ≥1.23 |
| Pillow | Обработка PNG, preview | ≥10.0 |
| opencv-python-headless | Предобработка подписи (HSV, adaptive threshold, morphology) | ≥4.8 |
| numpy | Матричные операции для fingerprint и OpenCV | ≥1.24 |
| simhash | 64-bit simhash документов | ≥2.1 |
| anthropic | Anthropic LLM API | ≥0.40 |
| openai | OpenAI LLM API | ≥1.35 |
| google-generativeai | Gemini API | ≥0.7 |
| langdetect | Определение языка документа | ≥1.0.9 |
| python-docx | DOCX → текст (резерв, LibreOffice предпочтителен) | ≥1.0 |
| pydantic | Модели данных | ≥2.5 |

### B.2 signfinder-api

| Библиотека | Для чего |
|-----------|----------|
| FastAPI ≥0.115 | Веб-фреймворк, OpenAPI автоматом |
| Uvicorn ≥0.32 | ASGI сервер |
| python-multipart | Multipart/form-data загрузка файлов |
| httpx | HTTP-клиент для async тестов |

### B.3 SignPDFMVPLocal (Streamlit)

| Библиотека | Для чего |
|-----------|----------|
| streamlit | UI фреймворк |
| streamlit-image-coordinates | Клик по изображению для ручной разметки |
| pandas | Таблица результатов пакетной обработки |
| requests | HTTP-клиент к API |
| Pillow | Превью подписи с белой подложкой |

### B.4 Почему LibreOffice headless (не python-docx)

python-docx теряет вёрстку и таблицы. LibreOffice даёт идентичный fingerprint с оригиналом. DOCX конвертируется в Streamlit контейнере **до** отправки в API — API получает только PDF.

### B.5 Технологический стек деплоя

| Компонент | Локально | Облако |
|-----------|----------|--------|
| Контейнер | Docker compose | GCP Cloud Run |
| Storage | LocalFilesystemStorage | GCSStorage |
| LLM API key | В llm_config.json или env | Secret Manager |
| Логи | stdout → docker logs | Cloud Logging |

---

**Конец документа. Версия концепции v2.0, июнь 2026.**
