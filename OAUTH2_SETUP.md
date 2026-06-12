# OAuth2 (XOAUTH2) — Инструкция по настройке

## Принцип

SignFinder использует SASL XOAUTH2 для IMAP/SMTP. Нужно один раз получить `refresh_token`,
затем вставить его в Настройки → Mail → OAuth2.
Access token обновляется автоматически (кэш до истечения).

---

## Google / Gmail

### Шаг 1 — Google Cloud Console

1. Открой [console.cloud.google.com](https://console.cloud.google.com)
2. Создай проект (или выбери существующий) — бесплатно
3. **APIs & Services → Library → Gmail API → Enable**
4. **APIs & Services → OAuth consent screen**
   - User Type: External
   - Заполни название, email
   - **Test users → + Add users** — добавь свой email
5. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Скачай JSON или скопируй `client_id` и `client_secret`

### Шаг 2 — Получить refresh_token

```bash
python get_refresh_token.py --provider google \
    --client-id YOUR_CLIENT_ID \
    --client-secret YOUR_CLIENT_SECRET
```

Откроется браузер → авторизуй доступ → в терминале появится `refresh_token`.

### Шаг 3 — Вставить в Настройки

Настройки → Mail → OAuth2 → Google → заполнить:
- User: `your@gmail.com`
- Client ID / Client Secret / Refresh Token

Хосты и endpoint подставляются автоматически из пресета.

---

## Microsoft 365 / Outlook

1. [portal.azure.com](https://portal.azure.com) → **Azure Active Directory → App registrations → New registration**
2. Redirect URI: `http://localhost:8080/callback` (Public client / native)
3. **API permissions → Add → Microsoft Graph → Delegated**:
   - `IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access`
4. **Grant admin consent** (или попроси администратора)
5. **Certificates & secrets → New client secret** → скопируй значение
6. Запусти `get_refresh_token.py --provider microsoft ...`

Scope: `https://outlook.office365.com/IMAP.AccessAsUser.All offline_access`

---

## Yandex

1. [oauth.yandex.ru/client/new](https://oauth.yandex.ru/client/new) — создай приложение
2. Платформа: **Веб-сервисы**, Callback URI: `http://localhost:8080/callback`
3. Доступы: **Яндекс.Почта (IMAP/SMTP)**
4. Скопируй `client_id` и `client_secret`
5. `get_refresh_token.py --provider yandex ...`

Scope: `mail:imap_full`

---

## Mail.ru

1. [o2.mail.ru/app](https://o2.mail.ru/app) — создай приложение
2. Redirect URI: `http://localhost:8080/callback`
3. Scope: `mail.imap`
4. `get_refresh_token.py --provider mailru ...`

---

## Rambler

1. [id.rambler.ru/oauth](https://id.rambler.ru/oauth) — создай приложение
2. Scope: `mail`
3. `get_refresh_token.py --provider rambler ...`

---

## Скрипт get_refresh_token.py

Запусти один раз, вставь полученный `refresh_token` в UI.
Скрипт живёт в `SignPDFMVPLocal/get_refresh_token.py`.
