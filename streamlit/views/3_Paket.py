"""Пакетная обработка договоров — SignFinder v1.12.1.

Загрузка до 100 PDF/DOCX → batch-анализ через POST /v1/analyze/batch →
таблица результатов (🟢🟡🔴, шаблон, score, зон, время). Drill-down по строке.
Кнопка «В разбор» кидает выбранный dok в страницу «Разбор» через razbor_pending.
FIX v1.12.1: DOCX конвертируется в PDF на стороне Streamlit (LibreOffice) перед
отправкой в API — fingerprint считается по тем же байтам что в авто-подписании.
"""
import os
import sys

import pandas as pd
import requests
import streamlit as st

from core.i18n import t

API_BASE = os.environ.get("API_URL", "http://api:8000")


@st.cache_data(ttl=60)
def _sf_version() -> str:
    try:
        r = requests.get(f"{API_BASE}/v1/version", timeout=3)
        return r.json().get("api_version", "?")
    except Exception:
        return "?"

if not st.session_state.get("auth"):
    st.warning(t("warn_login_required"))
    st.stop()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.api_client import get_api_client

st.title(t("batch_title"))
st.caption(t("batch_caption"))

MAX_FILES = 100

_TL_ICON = {"green": "🟢", "yellow": "🟡", "no_match": "🔴"}
_TL_LABEL = {
    "green":    t("tl_green"),
    "yellow":   t("tl_yellow"),
    "no_match": t("tl_no_match"),
}

if "batch_counter" not in st.session_state:
    st.session_state["batch_counter"] = 0


def _reset_batch():
    st.session_state.pop("batch_result", None)
    st.session_state.pop("batch_files_raw", None)
    st.session_state["batch_counter"] += 1


# ── Загрузка ──────────────────────────────────────────────────────────────────
uploader_key = f"batch_uploader_{st.session_state['batch_counter']}"
uploaded = st.file_uploader(
    t("batch_uploader"),
    type=["pdf", "docx"],
    accept_multiple_files=True,
    key=uploader_key,
)

col_run, col_reset = st.columns([2, 1])
with col_run:
    run_disabled = not uploaded
    if st.button(t("batch_btn_run").format(n=len(uploaded) if uploaded else 0),
                 type="primary", disabled=run_disabled, use_container_width=True):
        if len(uploaded) > MAX_FILES:
            st.error(t("batch_err_max", max=MAX_FILES, n=len(uploaded)))
        else:
            from core.parser import parse_document

            files = []
            converted_bytes = {}
            has_docx = any(f.name.lower().endswith(".docx") for f in uploaded)

            with st.spinner(t("batch_preparing") + (t("batch_converting") if has_docx else "")):
                for f in uploaded:
                    fname = f.name
                    raw = f.getvalue()
                    if fname.lower().endswith(".docx"):
                        try:
                            doc = parse_document(raw, fname)
                            file_bytes = doc.pdf_bytes
                        except Exception as e:
                            st.error(t("batch_err_convert", name=fname, err=e))
                            sys.stderr.write(f"[batch] docx_to_pdf {fname}: {e}\n")
                            continue
                    else:
                        file_bytes = raw
                    files.append((fname, file_bytes))
                    converted_bytes[fname] = file_bytes

            st.session_state["batch_files_raw"] = converted_bytes

            if not files:
                st.error(t("batch_err_no_files"))
            else:
                with st.spinner(t("batch_analyzing", n=len(files))):
                    try:
                        st.session_state["batch_result"] = get_api_client().analyze_batch(files)
                    except Exception as e:
                        st.error(t("batch_err_batch", err=e))
                        sys.stderr.write(f"[batch] analyze_batch: {e}\n")
with col_reset:
    if st.button(t("batch_btn_reset"), use_container_width=True):
        _reset_batch()
        st.rerun()


# ── Результаты ────────────────────────────────────────────────────────────────
result = st.session_state.get("batch_result")
if not result:
    st.stop()

st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric(t("metric_total"), result.get("total", 0))
c2.metric(t("metric_processed"), result.get("succeeded", 0))
c3.metric(t("metric_failed"), result.get("failed", 0))
items = result.get("items", [])
yellow_n = sum(1 for it in items
               if (it.get("analysis") or {}).get("traffic_light") == "yellow")
c4.metric(t("metric_review"), yellow_n)

# Локальные имена колонок для текущего языка
_col_file   = t("col_file")
_col_status = t("col_status")
_col_tpl    = t("col_template")
_col_score  = t("col_score")
_col_zones  = t("col_zones")
_col_time   = t("col_time")
_col_error  = t("col_error")

rows = []
for idx, it in enumerate(items):
    analysis = it.get("analysis") or {}
    tl = analysis.get("traffic_light", "no_match") if analysis else "no_match"
    mt = analysis.get("matched_template") or {}
    score = mt.get("best_match_score")
    rows.append({
        "#": idx,
        _col_file:   it.get("filename", "?"),
        _col_status: f"{_TL_ICON.get(tl, '🔴')} {_TL_LABEL.get(tl, tl)}",
        _col_tpl:    (mt.get("best_match_template_id") or "—")[:8],
        _col_score:  f"{int(score * 100)}%" if score is not None else "—",
        _col_zones:  len(analysis.get("anchors", [])) if analysis else 0,
        _col_time:   f"{it.get('elapsed_ms', 0)} мс",
        _col_error:  it.get("error") or "",
    })

df = pd.DataFrame(rows)
st.dataframe(df.drop(columns=["#"]), use_container_width=True, hide_index=True)

# ── Drill-down + действия ──────────────────────────────────────────────────────
st.divider()
st.subheader(t("batch_actions"))

options = [f"{r['#']}: {r[_col_file]} — {r[_col_status]}" for r in rows]
selected = st.selectbox(t("batch_select"), options=options, key="batch_select")
sel_idx = int(selected.split(":", 1)[0])
sel_item = items[sel_idx]
sel_analysis = sel_item.get("analysis") or {}
sel_tl = sel_analysis.get("traffic_light", "no_match") if sel_analysis else "no_match"
sel_fname = sel_item.get("filename", "?")

with st.expander(t("batch_details"), expanded=False):
    mt = sel_analysis.get("matched_template") or {}
    fp = sel_analysis.get("fingerprint") or {}
    st.write(f"{t('lbl_traffic_light')} {_TL_ICON.get(sel_tl)} {_TL_LABEL.get(sel_tl, sel_tl)}")
    if sel_item.get("error"):
        st.error(f"{t('lbl_api_error')} {sel_item['error']}")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(t("metric_candidates"), mt.get("candidates_count", 0))
    mc2.metric(t("col_score"), f"{int((mt.get('best_match_score') or 0) * 100)}%")
    mc3.metric(t("metric_anchors"), len(sel_analysis.get("anchors", [])))
    mc4.metric(t("metric_fp_pages"), fp.get("page_count", "—"))
    if fp:
        st.caption(t("lbl_fingerprint"))
        st.json({k: fp.get(k) for k in ("simhash", "jaccard_tokens", "page_count")
                 if k in fp}, expanded=False)
    our = sel_analysis.get("our_side") or {}
    if our:
        st.caption(f"{t('lbl_our_side')} **{our.get('legal_entity', '—')}** / {our.get('signer', '—')}")

# Кнопка «В разбор» — только если документ обработан (есть анализ)
can_razbor = bool(sel_analysis) and sel_tl != "no_match"
raw_files = st.session_state.get("batch_files_raw", {})

if st.button(t("btn_send_review"), type="primary", disabled=not can_razbor):
    pdf_bytes = raw_files.get(sel_fname)
    if not pdf_bytes:
        st.error(t("err_file_not_found"))
    else:
        st.session_state["razbor_pending"] = {
            "filename": sel_fname,
            "pdf_bytes": pdf_bytes,
            "language": None,
            "analysis": sel_analysis,
        }
        st.switch_page("views/5_Avto_podpisanie.py")

if not can_razbor:
    st.caption(t("hint_no_match_review"))

st.divider()
st.caption(f"SignFinder v{_sf_version()}")
