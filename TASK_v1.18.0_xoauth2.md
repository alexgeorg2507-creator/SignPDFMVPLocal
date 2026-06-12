# SignFinder v1.18.0 — XOAUTH2 для IMAP/SMTP (отладка на Google)

Прочитай `C:\work\CLAUDE.md` перед началом.

Это НОВАЯ фича, не фикс. Закрывает облачные Exchange Online / Gmail-без-App-Password.
Отладка на Google (бесплатно), перенос на остальных — сменой provider в UI.

---

## Контекст и принцип

Сейчас `ImapSource._connect()` делает `self._imap.login(user, password)` — basic auth.
OAuth2 над IMAP — это **SASL XOAUTH2** (открытый стандарт, RFC 7628), не фишка
Microsoft. Один механизм для всех провайдеров, различие только в token endpoint и scope.

**Принцип: XOAUTH2 добавляется РЯДОМ с basic auth, не вместо.** Существующий
basic-auth путь (on-prem Exchange, обычный IMAP) остаётся рабочим. Выбор способа —
через конфиг `auth_method: basic | xoauth2`.

Архитектурно это расширение адаптера `IntakeSource`, заложенное ещё в v1.16.

---

## Часть 1 — Модуль получения токена (новый файл)

Создать `signfinder-core/signfinder/intake/oauth2.py`:

```python
"""OAuth2 (XOAUTH2) для IMAP/SMTP. Получение access_token по refresh_token.

Провайдеро-независимый: endpoint/scope задаются в конфиге.
Все провайдеры используют одинаковый OAuth2 refresh-flow, разные URL.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
import json

logger = logging.getLogger(__name__)

# Известные провайдеры — token endpoint
TOKEN_ENDPOINTS = {
    "google":    "https://oauth2.googleapis.com/token",
    "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "yandex":    "https://oauth.yandex.ru/token",
    "mailru":    "https://oauth.mail.ru/token",
    "rambler":   "https://id.rambler.ru/oauth/token",
}


class OAuth2TokenProvider:
    """Хранит refresh_token, выдаёт свежий access_token (кэширует до истечения)."""

    def __init__(
        self,
        provider: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_endpoint: str = "",   # override; иначе из TOKEN_ENDPOINTS
    ) -> None:
        self._provider = provider
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._endpoint = token_endpoint or TOKEN_ENDPOINTS.get(provider, "")
        if not self._endpoint:
            raise ValueError(f"Unknown OAuth2 provider '{provider}', specify token_endpoint")
        self._access_token: str = ""
        self._expires_at: float = 0.0

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        self._refresh()
        return self._access_token

    def _refresh(self) -> None:
        data = urllib.parse.urlencode({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(self._endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        except Exception as e:
            raise RuntimeError(f"OAuth2 token refresh failed ({self._provider}): {e}")
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + int(payload.get("expires_in", 3600))
        logger.info("OAuth2 token refreshed for %s (expires in %ss)",
                    self._provider, payload.get("expires_in"))


def build_xoauth2_string(user: str, access_token: str) -> bytes:
    """Формирует SASL XOAUTH2 строку для imaplib.authenticate / SMTP."""
    raw = f"user={user}\x01auth=Bearer {access_token}\x01\x01"
    return raw.encode()
```

Только stdlib (urllib) — без новых зависимостей.

---

## Часть 2 — ImapSource: ветвление auth

`signfinder-core/signfinder/intake/imap_source.py`.

### 2.1 Конструктор — добавить OAuth-параметры (опциональные)

```python
def __init__(
    self,
    host: str, port: int, user: str, password: str, ssl: bool, folder_in: str,
    auth_method: str = "basic",          # "basic" | "xoauth2"
    oauth2_provider: str = "",
    oauth2_client_id: str = "",
    oauth2_client_secret: str = "",
    oauth2_refresh_token: str = "",
    oauth2_token_endpoint: str = "",
) -> None:
    ...
    self._auth_method = auth_method
    self._oauth = None
    if auth_method == "xoauth2":
        from signfinder.intake.oauth2 import OAuth2TokenProvider
        self._oauth = OAuth2TokenProvider(
            provider=oauth2_provider,
            client_id=oauth2_client_id,
            client_secret=oauth2_client_secret,
            refresh_token=oauth2_refresh_token,
            token_endpoint=oauth2_token_endpoint,
        )
```

### 2.2 _connect() — ветвление login vs authenticate

```python
        if self._ssl:
            self._imap = imaplib.IMAP4_SSL(self._host, self._port)
        else:
            self._imap = imaplib.IMAP4(self._host, self._port)

        if self._auth_method == "xoauth2" and self._oauth is not None:
            from signfinder.intake.oauth2 import build_xoauth2_string
            token = self._oauth.get_access_token()
            auth_bytes = build_xoauth2_string(self._user, token)
            typ, _ = self._imap.authenticate("XOAUTH2", lambda _: auth_bytes)
            if typ != "OK":
                raise RuntimeError(f"IMAP XOAUTH2 auth failed: {typ}")
            logger.info("IMAP XOAUTH2 logged in as %s (%s)", self._user, self._oauth._provider)
        else:
            self._imap.login(self._user, self._password)
            logger.info("IMAP logged in as %s (basic)", self._user)
```

---

## Часть 3 — SmtpSink: тот же XOAUTH2

`signfinder-core/signfinder/intake/smtp_sink.py`.

Аналогичное ветвление: basic → `server.login(user, password)`; xoauth2 →
```python
import base64
from signfinder.intake.oauth2 import build_xoauth2_string
auth_string = build_xoauth2_string(user, token)
server.docmd("AUTH", "XOAUTH2 " + base64.b64encode(auth_string).decode())
```
(проверь точный синтаксис smtplib — возможно `server.auth("XOAUTH2", lambda: auth_string)`).
Принять те же oauth2-параметры в конструкторе SmtpSink.

---

## Часть 4 — Конфиг mail_config

### 4.1 Pydantic MailConfig (signfinder-api/app/models/settings.py)

```python
auth_method: str = "basic"          # basic | xoauth2
oauth2_provider: str = ""           # google | microsoft | yandex | mailru | rambler
oauth2_client_id: str = ""
oauth2_client_secret: str = ""
oauth2_refresh_token: str = ""
oauth2_token_endpoint: str = ""     # override, опционально
```

### 4.2 Агент — load_mail_config + проброс

`agent/app/config.py` `load_mail_config()` — читать новые поля (JSON приоритет, env fallback).
`agent/app/mailbox.py` `_get_source()` / `_get_sink()` — пробросить oauth2-поля.

---

## Часть 5 — UI: настройки OAuth2 (4_Nastroyki.py, таб Mail)

**ВАЖНО по компоновке:** НЕ вываливать все поля всех провайдеров на страницу.
Логика прогрессивного раскрытия:

1. Радио способа аутентификации: **Пароль (basic)** / **OAuth2 (XOAUTH2)**
2. Если basic → показать обычное поле пароля (как сейчас), OAuth-блок скрыт
3. Если xoauth2 → скрыть пароль, показать **дропдаун провайдера** (5 шт)
4. Только ПОСЛЕ выбора провайдера в дропдауне → показать поля этого провайдера

То есть на экране одновременно — настройки ТОЛЬКО выбранного провайдера, не всех.

### 5.1 Пресеты провайдеров

```python
_OAUTH_PRESETS = {
    "google": {
        "label": "Google / Gmail",
        "imap_host": "imap.gmail.com", "imap_port": 993,
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "scope_hint": "https://mail.google.com/",
    },
    "microsoft": {
        "label": "Microsoft 365 / Outlook",
        "imap_host": "outlook.office365.com", "imap_port": 993,
        "smtp_host": "smtp.office365.com", "smtp_port": 587,
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope_hint": "https://outlook.office365.com/IMAP.AccessAsUser.All offline_access",
    },
    "yandex": {
        "label": "Yandex",
        "imap_host": "imap.yandex.ru", "imap_port": 993,
        "smtp_host": "smtp.yandex.ru", "smtp_port": 465,
        "token_endpoint": "https://oauth.yandex.ru/token",
        "scope_hint": "mail:imap_full",
    },
    "mailru": {
        "label": "Mail.ru",
        "imap_host": "imap.mail.ru", "imap_port": 993,
        "smtp_host": "smtp.mail.ru", "smtp_port": 465,
        "token_endpoint": "https://oauth.mail.ru/token",
        "scope_hint": "mail.imap",
    },
    "rambler": {
        "label": "Rambler",
        "imap_host": "imap.rambler.ru", "imap_port": 993,
        "smtp_host": "smtp.rambler.ru", "smtp_port": 465,
        "token_endpoint": "https://id.rambler.ru/oauth/token",
        "scope_hint": "mail",
    },
}
```

### 5.2 Прогрессивное раскрытие

```python
auth_method = st.radio(
    "Способ аутентификации",
    options=["basic", "xoauth2"],
    format_func=lambda x: "Пароль (basic)" if x == "basic" else "OAuth2 (XOAUTH2)",
    horizontal=True, key="mail_auth_method", on_change=_autosave_mail,
)

if auth_method == "basic":
    # обычное поле пароля (как сейчас)
    ...
else:
    provider = st.selectbox(
        "Провайдер OAuth2",
        options=list(_OAUTH_PRESETS.keys()),
        format_func=lambda p: _OAUTH_PRESETS[p]["label"],
        key="mail_oauth2_provider", on_change=_on_provider_change,
    )
    preset = _OAUTH_PRESETS[provider]
    st.caption(f"Хост IMAP: {preset['imap_host']}:{preset['imap_port']} · "
               f"SMTP: {preset['smtp_host']}:{preset['smtp_port']}")
    st.caption(f"Scope для refresh_token: `{preset['scope_hint']}`")
    # Поля только выбранного провайдера — НЕ дефолтные хосты/порты/endpoint на экране,
    # они берутся из пресета автоматически. Оператор вводит ТОЛЬКО:
    st.text_input("User (email)", key="mail_imap_user", on_change=_autosave_mail)
    st.text_input("Client ID", key="mail_oauth2_client_id", on_change=_autosave_mail)
    st.text_input("Client Secret", type="password",
                  key="mail_oauth2_client_secret", on_change=_autosave_mail)
    st.text_input("Refresh Token", type="password",
                  key="mail_oauth2_refresh_token", on_change=_autosave_mail)
    st.caption("Refresh token получается одноразово — см. OAUTH2_SETUP.md")
```

### 5.3 `_on_provider_change` — подставить дефолты из пресета

При смене провайдера записать в session_state и в сохраняемый конфиг
imap_host/port, smtp_host/port, token_endpoint из пресета (оператор их НЕ видит
полями — они проставляются автоматически, скрыто). Затем `_autosave_mail()`.

```python
def _on_provider_change():
    p = st.session_state.get("mail_oauth2_provider", "google")
    preset = _OAUTH_PRESETS[p]
    st.session_state["mail_imap_host"] = preset["imap_host"]
    st.session_state["mail_imap_port"] = preset["imap_port"]
    st.session_state["mail_smtp_host"] = preset["smtp_host"]
    st.session_state["mail_smtp_port"] = preset["smtp_port"]
    st.session_state["mail_oauth2_token_endpoint"] = preset["token_endpoint"]
    _autosave_mail()
```

Принцип: на экране — дропдаун + 4 поля (user, client_id, secret, refresh_token).
Всё остальное (хосты, порты, endpoint) — дефолты из пресета, скрыто, проставляется
автоматически. Можно добавить «⚙️ Расширенные» expander для ручного override хостов.

### 5.4 _MAIL_DEF и _autosave_mail

Добавить ключи: auth_method, oauth2_provider, oauth2_client_id, oauth2_client_secret,
oauth2_refresh_token, oauth2_token_endpoint. Секреты (client_secret, refresh_token) —
не затирать пустым при автосохранении, как imap_password.

---

## Часть 6 — Документация (новый файл OAUTH2_SETUP.md)

`SignPDFMVPLocal/OAUTH2_SETUP.md` — инструкции по провайдерам.

**Google** (основной для отладки):
1. Google Cloud Console → проект (бесплатно)
2. Enable Gmail API
3. OAuth consent screen → External → добавить себя в test users
4. Credentials → OAuth client ID → Desktop app → client_id + client_secret
5. refresh_token одноразово (скрипт ниже), scope `https://mail.google.com/`
6. Вставить в Настройки → Mail → OAuth2 → Google

**Microsoft**: Azure Portal → App registrations → client_id/secret,
permissions IMAP.AccessAsUser.All + offline_access, scope из пресета.

**Yandex / Mail.ru / Rambler**: кабинет OAuth провайдера → создать приложение →
client_id/secret, scope из пресета (`mail:imap_full` / `mail.imap` / `mail`).

Приложить скрипт `get_refresh_token.py` (one-shot, localhost-redirect, браузер,
печатает refresh_token). Параметр `--provider` выбирает authorize/token URL + scope.
Только stdlib + браузер.

---

## Отладка на Google (порядок)

1. Реализовать Части 1-4
2. По OAUTH2_SETUP.md получить refresh_token для `alexgeorg2507@gmail.com`
3. Настройки → Mail → OAuth2 → Google → user + client_id + secret + refresh_token
4. Тот же ящик, те же письма в SignfinderIn
5. Агент по XOAUTH2 → опрос → подпись → раскладка
6. Лог: `IMAP XOAUTH2 logged in as ... (google)`

Microsoft/Yandex/Mail.ru/Rambler — смена провайдера в дропдауне, код тот же.

---

## Bump + деплой

```powershell
cd C:\work\signfinder-core
git add -A
git commit -m "v1.18.0: XOAUTH2 (google/microsoft/yandex/mailru/rambler)"
git push origin main

cd C:\work\SignPDFMVPLocal
docker compose build --no-cache api
docker compose build agent streamlit
docker compose up -d --force-recreate
```

Bump: core `__init__.py` + `pyproject.toml` → 1.18.0, api main.py, CLAUDE.md.

## Тест

1. basic auth (App Password) — РАБОТАЕТ как раньше (регрессия)
2. OAuth2 Google — подключение, опрос, подпись
3. Лог: `XOAUTH2 logged in ... (google)`
4. Дропдаун: на экране поля ТОЛЬКО выбранного провайдера, не всех
5. Смена провайдера подставляет хосты/порты/endpoint скрыто (дефолты пресета)

## TECH_DEBT

TD-06 уже обновлён КАПСОМ (секреты OAuth2 в открытом mail_config.json). Не трогать.

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
