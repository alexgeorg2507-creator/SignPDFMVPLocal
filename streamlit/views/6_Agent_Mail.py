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

from core.i18n import t

try:
    import zoneinfo
    _TZ = zoneinfo.ZoneInfo("Asia/Tbilisi")
except Exception:
    _TZ = timezone.utc


if not st.session_state.get("auth"):
    st.warning(t("warn_login_required"))
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
st.title(t("agent_title"))

status = _api_get("/v1/agent/status")
if status.get("_timeout"):
    st.info(t("agent_timeout"))
elif status.get("error"):
    st.warning(t("agent_unavailable", err=status['error']))
else:
    _polling = bool(status.get("running"))
    c1, c2, c3, c4 = st.columns(4)
    if _polling:
        c1.metric(t("metric_status"), t("status_polling"))
    else:
        c1.metric(t("metric_status"),
                  t("status_ok") if status.get("imap_configured") else t("status_no_imap"))
    c2.metric(t("metric_last_poll"), _fmt_dt(status.get("last_poll")))
    c3.metric(t("metric_last_count"), status.get("last_poll_count", 0))
    c4.metric(t("metric_queue"), status.get("queue_count", "?"))
    if _polling:
        st.info(t("info_polling"))
    if not status.get("imap_configured"):
        st.info(t("info_imap_hint"))

tab_queue, tab_log = st.tabs([t("tab_queue"), t("tab_log")])

# ── ОЧЕРЕДЬ ───────────────────────────────────────────────────────────────────
with tab_queue:
    col_h, col_btn, col_refresh = st.columns([4, 2, 2])
    with col_h:
        st.subheader(t("queue_title"))
    with col_btn:
        if st.button(t("btn_poll_now"), use_container_width=True):
            res = _api_post("/v1/agent/poll-now")
            if "error" in res:
                st.error(t("err_poll", err=res['error']))
            elif res.get("status") == "already_running":
                st.warning(t("warn_poll_running"))
            else:
                st.info(t("info_poll_started"))
    with col_refresh:
        if st.button(t("btn_refresh"), use_container_width=True, key="queue_refresh"):
            st.rerun()

    queue = _read_queue()
    items = queue.get("items", [])

    if not items:
        st.info(t("queue_empty"))
    else:
        for item in items:
            uid = item.get("uid", "")
            subject = item.get("subject", "")
            sender = item.get("sender", "")
            received = _fmt_dt(item.get("received_at"))
            docs = item.get("documents", [])

            with st.container(border=True):
                st.markdown(f"**{subject or t('lbl_no_subject')}**")
                st.caption(f"{t('lbl_from')} {sender}  ·  {received}  ·  {t('lbl_pdf_count')} {len(docs)}")
                for doc in docs:
                    light = doc.get("light", "yellow")
                    tpl = (doc.get("template") or "")[:8]
                    score = doc.get("score")
                    pct = f" {int(score*100)}%" if score is not None else ""
                    st.caption(f"  {_TL_ICON.get(light,'🟡')} {doc.get('name','?')} · "
                               f"{tpl or 'нет шаблона'}{pct} · {doc.get('anchor_count',0)} мест")

                cb1, cb2, cb3, cb4 = st.columns(4)

                with cb1:
                    if st.button(t("btn_confirm"), key=f"confirm_{uid}",
                                 use_container_width=True, type="primary"):
                        res = _api_post("/v1/agent/resolve", {"uid": uid, "action": "confirm"})
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.success(t("ok_confirm"))
                            st.rerun()

                with cb2:
                    if st.button(t("btn_reject"), key=f"reject_{uid}", use_container_width=True):
                        res = _api_post("/v1/agent/resolve", {"uid": uid, "action": "reject"})
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.warning(t("ok_reject"))
                            st.rerun()

                with cb3:
                    if st.button(t("btn_load"), key=f"load_{uid}", use_container_width=True):
                        st.session_state[f"_loaded_{uid}"] = _api_get(f"/v1/agent/queue/{uid}")

                with cb4:
                    if st.button(t("btn_to_review"), key=f"razbor_{uid}", use_container_width=True):
                        _rd = _api_get(f"/v1/agent/queue/{uid}")
                        _origs = _rd.get("original_pdfs", [])
                        if _origs:
                            _send_to_razbor(uid, _origs[0], _rd.get("item", item))
                        else:
                            st.warning(t("warn_no_originals"))

                data = st.session_state.get(f"_loaded_{uid}")
                if data:
                    for sp in data.get("signed_pdfs", []):
                        st.download_button(f"💾 {sp['name']}", data=base64.b64decode(sp["b64"]),
                                           file_name=sp["name"], mime="application/pdf",
                                           key=f"dl_{uid}_{sp['name']}")

                    st.caption(t("lbl_resign"))
                    for orig in data.get("original_pdfs", []):
                        if st.button(f"✏️ {orig['name']}", key=f"resign_{uid}_{orig['name']}",
                                     use_container_width=True):
                            _send_to_razbor(uid, orig, data.get("item", {}))
                    if not data.get("original_pdfs"):
                        st.caption(t("warn_no_originals"))

# ── ЖУРНАЛ ────────────────────────────────────────────────────────────────────
with tab_log:
    col_h2, col_flt, col_btn2 = st.columns([4, 3, 2])
    with col_h2:
        st.subheader(t("log_title"))
    with col_flt:
        _all_label = t("log_filter_all")
        filter_light = st.selectbox(t("log_filter"),
                                    [_all_label, "🟢 green", "🟡 yellow", "🔴 no_match"],
                                    label_visibility="collapsed")
    with col_btn2:
        if st.button(t("btn_refresh"), use_container_width=True):
            st.rerun()

    light_map = {"🟢 green": "green", "🟡 yellow": "yellow", "🔴 no_match": "no_match"}
    flt = light_map.get(filter_light)
    entries = _read_log(n=100)
    if flt:
        entries = [e for e in entries if any(p.get("light") == flt for p in e.get("pdfs", []))]

    if not entries:
        st.info(t("log_empty"))
    else:
        import pandas as pd
        _col_time    = t("col_time_log")
        _col_subject = t("col_subject")
        _col_pdf     = t("col_pdf")
        _col_status  = t("col_status")
        _col_tpl     = t("col_template")
        _col_score   = t("col_score")
        _col_dest    = t("col_dest")
        _col_error   = t("col_error")
        rows = []
        for e in reversed(entries):
            pdfs = e.get("pdfs", [])
            lights = [_TL_ICON.get(p.get("light", ""), "?") for p in pdfs]
            templates = list({(p.get("template") or "")[:8] for p in pdfs if p.get("template")})
            scores = [p.get("score") for p in pdfs if p.get("score") is not None]
            rows.append({
                _col_time:    _fmt_dt(e.get("ts")),
                _col_subject: (e.get("subject") or "")[:40],
                _col_pdf:     len(pdfs),
                _col_status:  " ".join(lights),
                _col_tpl:     ", ".join(templates) or "—",
                _col_score:   f"{int(scores[0]*100)}%" if scores else "—",
                _col_dest:    (e.get("destination") or "").replace("Signfinder", ""),
                _col_error:   (e.get("error") or "")[:40],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.caption(f"SignFinder v{_sf_version()}")
