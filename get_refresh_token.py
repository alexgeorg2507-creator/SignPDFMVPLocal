#!/usr/bin/env python3
"""One-shot helper: получить refresh_token для OAuth2 через localhost redirect.

Использование:
    python get_refresh_token.py --provider google \
        --client-id YOUR_CLIENT_ID \
        --client-secret YOUR_CLIENT_SECRET

Поддерживаемые провайдеры: google, microsoft, yandex, mailru, rambler
Только stdlib + браузер.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import urllib.parse
import urllib.request
import webbrowser

PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://mail.google.com/",
    },
    "microsoft": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "https://outlook.office365.com/IMAP.AccessAsUser.All offline_access",
    },
    "yandex": {
        "auth_url": "https://oauth.yandex.ru/authorize",
        "token_url": "https://oauth.yandex.ru/token",
        "scope": "mail:imap_full",
    },
    "mailru": {
        "auth_url": "https://oauth.mail.ru/login",
        "token_url": "https://oauth.mail.ru/token",
        "scope": "mail.imap",
    },
    "rambler": {
        "auth_url": "https://id.rambler.ru/oauth/authorize",
        "token_url": "https://id.rambler.ru/oauth/token",
        "scope": "mail",
    },
}

REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

_auth_code: list[str] = []


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [""])[0]
        if code:
            _auth_code.append(code)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>OK. Закрой эту вкладку и вернись в терминал.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received.")

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=list(PROVIDERS))
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    prov = PROVIDERS[args.provider]
    auth_params = urllib.parse.urlencode({
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": prov["scope"],
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"{prov['auth_url']}?{auth_params}"

    print(f"\nОткрываю браузер: {auth_url}\n")
    webbrowser.open(auth_url)

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.handle_request()

    if not _auth_code:
        print("Код авторизации не получен.")
        return

    code = _auth_code[0]
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(prov["token_url"], data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())

    refresh_token = payload.get("refresh_token", "")
    if not refresh_token:
        print("Ошибка: refresh_token отсутствует в ответе.")
        print(json.dumps(payload, indent=2))
        return

    print("\n" + "=" * 60)
    print("refresh_token:")
    print(refresh_token)
    print("=" * 60)
    print("\nВставь это значение в Настройки → Mail → OAuth2 → Refresh Token")


if __name__ == "__main__":
    main()
