"""Страница «Агент Mail» — SignFinder v1.17.4.

Две вкладки:
  Очередь разбора — жёлтые письма, ожидающие оператора
  Журнал          — история обработки
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

import requests
import streamlit as st

try:
    import zoneinfo
    _TZ = zoneinfo.ZoneInfo("Asia/Tbilisi")
except Exception:
    _TZ = timezone.utc


if not st.session_state.get("auth"):
    st.warning("Войдите через главную страницу.")
    st.stop()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.api_client import get_api_client

API_BASE = os.environ.get("API_URL", "http://api:8000")


@st.cache_data(ttl=60)
def _sf_version() -> str:
    try:
        r = requests.get(f"{API_BASE}/v1/version", timeout=3)
        return r.json().get("api_version", "?")
    except Exception:
        return "?"
AGENT_DATA_DIR = os.environ.get("AGENT_DATA_DIR", "/app/agent_data")
QUEUE_FILE = os.path.join(AGENT_DATA_DIR, "review_queue.json")
LOG_FILE = os.path.join(AGENT_DATA_DIR, "agent_log.jsonl")

_TL_ICON = {"green": "🟢", "yellow": "🟡", "no_match": "🔴"}


def _fmt_dt(iso: str | None) -> str:
    """UTC из журнала → местное время (Asia/Tbilisi, UTC+4)."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_TZ).strftime("%d.%m %H:%M")
    except Exception:
        return iso[:16]


def _api_get(path: str) -> dict:
    client = get_api_client()
    try:
        r = requests.get(f"{API_BASE}{path}",
                         headers={"Authorization": f"Bearer {client.api_key}"}, timeout=5)
        return r.json() if r.ok else {"error": f"{r.status_code}"}
    except requests.exceptions.Timeout:
        return {"_timeout": True}
    except Exception as e:
        return {"error": str(e)}


def _api_post(path: str, body: dict | None = None) -> dict:
    client = get_api_client()
    try:
        r = requests.post(f"{API_BASE}{path}",
                          headers={"Authorization": f"Bearer {client.api_key}"},
                          json=body, timeout=30)
        return r.json() if r.ok else {"error": f"{r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _send_to_razbor(uid: str, orig: dict, item: dict) -> None:
    """Грузит оригинальный PDF жёлтого письма в «Разбор и подписание» для ручной
    переразметки. Сохранённые якоря из очереди передаются как стартовая разметка."""
    import re as _re
    pdf_bytes = base64.b64decode(orig["b64"])

    # Сопоставить оригинал (имя слугифицировано на диске) с документом в очереди.
    docs = item.get("documents", [])
    oname = orig["name"]
    matched = next((d for d in docs if d.get("name") == oname), None)
    if matched is None:
        def _slug(s: str) -> str:
            return _re.sub(r"[^A-Za-z0-9._-]", "_", s)[:80]
        matched = next((d for d in docs if _slug(d.get("name", "")) == oname), None)
    if matched is None and len(docs) == 1:
        matched = docs[0]
    matched = matched or {}

    analysis = {
        "anchors": matched.get("anchors", []),
        "traffic_light": matched.get("light", "yellow"),
        "matched_template": {
            "traffic_light": matched.get("light"),
            "best_match_template_id": matched.get("template") or None,
            "best_match_score": matched.get("score"),
        },
        "fingerprint": None,
        "our_side": None,
    }
    st.session_state["razbor_pending"] = {
        "filename": matched.get("name") or oname,
        "pdf_bytes": pdf_bytes,
        "language": None,
        "analysis": analysis,
    }
    st.switch_page("views/5_Avto_podpisanie.py")


def _read_queue() -> dict:
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"items": []}
    except Exception:
        return _api_get("/v1/agent/queue") or {"items": []}


def _read_log(n: int = 100) -> list[dict]:
    entries = []
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
                if len(entries) >= n:
                    break
            except Exception:
                continue
        return list(reversed(entries))
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
st.title("📧 Агент Mail")

status = _api_get("/v1/agent/status")
if status.get("_timeout"):
    st.info("⏳ API занят — возможно идёт обработка писем. Нажмите «Обновить» через ~30 сек.")
elif status.get("error"):
    st.warning(f"Агент недоступен: {status['error']}")
else:
    _polling = bool(status.get("running"))
    c1, c2, c3, c4 = st.columns(4)
    if _polling:
        c1.metric("Статус", "🔄 Идёт опрос…")
    else:
        c1.metric("Статус", "🟢 Работает" if status.get("imap_configured") else "⚠️ IMAP не настроен")
    c2.metric("Последний опрос", _fmt_dt(status.get("last_poll")))
    c3.metric("Обработано (посл.)", status.get("last_poll_count", 0))
    c4.metric("В очереди", status.get("queue_count", "?"))
    if _polling:
        st.info("🔄 Опрос идёт в фоне. Нажмите «Обновить» через ~30 сек, чтобы увидеть новые письма.")
    if not status.get("imap_configured"):
        st.info("Настройте IMAP_HOST, IMAP_USER, IMAP_PASSWORD в `.env` и пересоберите агент.")

tab_queue, tab_log = st.tabs(["📋 Очередь разбора", "📜 Журнал"])

# ── ОЧЕРЕДЬ ───────────────────────────────────────────────────────────────────
with tab_queue:
    col_h, col_btn, col_refresh = st.columns([4, 2, 2])
    with col_h:
        st.subheader("Письма, требующие проверки оператором")
    with col_btn:
        if st.button("📨 Опросить почту сейчас", use_container_width=True):
            res = _api_post("/v1/agent/poll-now")
            if "error" in res:
                st.error(f"Ошибка: {res['error']}")
            elif res.get("status") == "already_running":
                st.warning("🔄 Опрос уже идёт — дождитесь завершения.")
            else:
                st.info("⏳ Опрос запущен в фоне. Письма появятся по мере обработки — "
                        "нажмите «Обновить» через ~30 сек.")
    with col_refresh:
        if st.button("🔄 Обновить", use_container_width=True, key="queue_refresh"):
            st.rerun()

    queue = _read_queue()
    items = queue.get("items", [])

    if not items:
        st.info("Очередь пуста.")
    else:
        for item in items:
            uid = item.get("uid", "")
            subject = item.get("subject", "")
            sender = item.get("sender", "")
            received = _fmt_dt(item.get("received_at"))
            docs = item.get("documents", [])

            with st.container(border=True):
                st.markdown(f"**{subject or '(без темы)'}**")
                st.caption(f"От: {sender}  ·  {received}  ·  PDF: {len(docs)}")
                for doc in docs:
                    light = doc.get("light", "yellow")
                    tpl = (doc.get("template") or "")[:8]
                    score = doc.get("score")
                    pct = f" {int(score*100)}%" if score is not None else ""
                    st.caption(f"  {_TL_ICON.get(light,'🟡')} {doc.get('name','?')} · "
                               f"{tpl or 'нет шаблона'}{pct} · {doc.get('anchor_count',0)} мест")

                cb1, cb2, cb3, cb4 = st.columns(4)

                with cb1:
                    if st.button("✅ Подтвердить", key=f"confirm_{uid}",
                                 use_container_width=True, type="primary"):
                        res = _api_post("/v1/agent/resolve", {"uid": uid, "action": "confirm"})
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.success("→ Green")
                            st.rerun()

                with cb2:
                    if st.button("❌ Отклонить", key=f"reject_{uid}", use_container_width=True):
                        res = _api_post("/v1/agent/resolve", {"uid": uid, "action": "reject"})
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.warning("→ Red")
                            st.rerun()

                with cb3:
                    if st.button("📥 Загрузить", key=f"load_{uid}", use_container_width=True):
                        st.session_state[f"_loaded_{uid}"] = _api_get(f"/v1/agent/queue/{uid}")

                with cb4:
                    if st.button("✏️ В разбор", key=f"razbor_{uid}", use_container_width=True):
                        _rd = _api_get(f"/v1/agent/queue/{uid}")
                        _origs = _rd.get("original_pdfs", [])
                        if _origs:
                            _send_to_razbor(uid, _origs[0], _rd.get("item", item))
                        else:
                            st.warning("⚠️ Оригиналы недоступны (старое письмо).")

                data = st.session_state.get(f"_loaded_{uid}")
                if data:
                    for sp in data.get("signed_pdfs", []):
                        st.download_button(f"💾 {sp['name']}", data=base64.b64decode(sp["b64"]),
                                           file_name=sp["name"], mime="application/pdf",
                                           key=f"dl_{uid}_{sp['name']}")

                    st.caption("Переразметить и переподписать вручную:")
                    for orig in data.get("original_pdfs", []):
                        if st.button(f"✏️ {orig['name']}", key=f"resign_{uid}_{orig['name']}",
                                     use_container_width=True):
                            _send_to_razbor(uid, orig, data.get("item", {}))
                    if not data.get("original_pdfs"):
                        st.caption("⚠️ Оригиналы недоступны (старое письмо).")

# ── ЖУРНАЛ ────────────────────────────────────────────────────────────────────
with tab_log:
    col_h2, col_flt, col_btn2 = st.columns([4, 3, 2])
    with col_h2:
        st.subheader("История обработки")
    with col_flt:
        filter_light = st.selectbox("Фильтр", ["все", "🟢 green", "🟡 yellow", "🔴 no_Match"],
                                    label_visibility="collapsed")
    with col_btn2:
        if st.button("🔄 Обновить", use_container_width=True):
            st.rerun()

    light_map = {"🟢 green": "green", "🟡 yellow": "yellow", "🔴 no_match": "no_match"}
    flt = light_map.get(filter_light)
    entries = _read_log(n=100)
    if flt:
        entries = [e for e in entries if any(p.get("light") == flt for p in e.get("pdfs", []))]

    if not entries:
        st.info("Журнал пуст.")
    else:
        import pandas as pd
        rows = []
        for e in reversed(entries):
            pdfs = e.get("pdfs", [])
            lights = [_TL_ICON.get(p.get("light", ""), "?") for p in pdfs]
            templates = list({(p.get("template") or "")[:8] for p in pdfs if p.get("template")})
            scores = [p.get("score") for p in pdfs if p.get("score") is not None]
            rows.append({
                "Время": _fmt_dt(e.get("ts")),
                "Тема": (e.get("subject") or "")[:40],
                "PDF": len(pdfs),
                "Статус": " ".join(lights),
                "Шаблон": ", ".join(templates) or "—",
                "Score": f"{int(scores[0]*100)}%" if scores else "—",
                "→ Папка": (e.get("destination") or "").replace("Signfinder", ""),
                "Ошибка": (e.get("error") or "")[:40],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption(f"SignFinder v{_sf_version()}")
