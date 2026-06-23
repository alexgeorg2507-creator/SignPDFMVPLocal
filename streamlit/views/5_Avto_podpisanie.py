"""Пакетная обработка и авто-подписание — SignFinder v1.14.0.

Три вкладки:
  Пакет         — загрузка до 100 PDF, batch-анализ, таблица результатов
  Разбор        — одиночный разбор/правка/подпись (логика v1.11)
  Тестирование — заглушка (v1.13)
«Пакет» кидает выбранный жёлтый dok в «Разбор» через razbor_pending.
v1.14.0: preview показывает маркер места подписи из sign_mode.
"""
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import requests
import streamlit as st
import streamlit.components.v1 as _components

from core.i18n import t

SUPPORTED_LANGUAGES = ("ru", "en", "pl", "mk")
API_BASE = os.environ.get("API_URL", "http://api:8000")


@st.cache_data(ttl=60)
def _sf_version() -> str:
    try:
        r = requests.get(f"{API_BASE}/v1/version", timeout=3)
        return r.json().get("api_version", "?")
    except Exception:
        return "?"


def _build_template_name(our_side: dict, language: str) -> str:
    """Читаемое имя шаблона: 'Договор с ООО Ромашка ru (08.06.2026)'."""
    from datetime import date
    date_str = date.today().strftime("%d.%m.%Y")
    our_entity = (our_side.get("legal_entity") or "").strip().lower()
    our_roles = {r.strip().lower() for r in (our_side.get("roles") or []) if r}
    counterparty = ""
    for p in (our_side.get("all_parties") or []):
        if not isinstance(p, dict):
            continue
        le = (p.get("legal_entity") or "").strip()
        role = (p.get("role") or "").strip()
        if le and le.lower() == our_entity:
            continue
        if role and role.lower() in our_roles:
            continue
        counterparty = le or role
        break
    if counterparty:
        return f"Договор с {counterparty[:40]} {language} ({date_str})"
    return f"Договор {language} ({date_str})"


if not st.session_state.get("auth"):
    st.warning(t("warn_login_required"))
    st.stop()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.api_client import get_api_client


def _default_page_idx(total_pages: int) -> int:
    """Return initial page index from sign-mode setting (last page by default)."""
    try:
        mode = get_api_client().get_sign_mode()
        return (total_pages - 1) if mode.get("default_page", "last") == "last" else 0
    except Exception:
        return total_pages - 1

def _signature_for_current_doc():
    """PNG подписи детектированного подписанта ТЕКУЩЕГО документа.

    Берём по detected_signer_id из auto_analyze_result (а не из единого
    session-глобала signature_png) — иначе при ингесте из пакета/очереди
    (_ingest_pending_from_batch не трогает signature_png) подпись в превью
    оставалась от предыдущего документа → разные доки показывали одну подпись.
    Кэш по signer_id сбрасывается при загрузке нового документа (_reset_pipeline),
    поэтому смена подписи в Настройках подхватывается на следующем документе.
    """
    ar = st.session_state.get("auto_analyze_result") or {}
    signer = ar.get("detected_signer_id") or "default"
    cache = st.session_state.setdefault("_sig_png_cache", {})
    if signer not in cache:
        try:
            cache[signer] = get_api_client().get_signature_png(signer)
        except Exception as _e:
            sys.stderr.write(f"[auto_sign] sig fetch {signer}: {_e}\n")
            cache[signer] = None
    return cache[signer]


if "signature_png" not in st.session_state:
    try:
        png = get_api_client().get_signature_png("default")
        if png:
            st.session_state["signature_png"] = png
    except Exception as _e:
        sys.stderr.write(f"[auto_sign] signature preload: {_e}\n")

if not st.session_state.get("signature_png"):
    st.error(t("warn_no_signature"))
    st.stop()

if "upload_counter" not in st.session_state:
    st.session_state["upload_counter"] = 0


def _make_anchor(d: dict) -> SimpleNamespace:
    a = SimpleNamespace(**d)
    if not isinstance(getattr(a, "bbox", None), (list, tuple)):
        a.bbox = [0.0, 0.0, 100.0, 20.0]
    return a


def _dedup_anchors(anchors: list) -> list:
    """Убирает дубли якорей. Три прохода."""
    seen_bbox: set = set()
    step1: list = []
    for a in anchors:
        bbox = getattr(a, "bbox", None) or [0, 0, 0, 0]
        key = (
            str(getattr(a, "page_hint", "0")),
            round(float(bbox[0]), 1), round(float(bbox[1]), 1),
            round(float(bbox[2]), 1), round(float(bbox[3]), 1),
        )
        if key not in seen_bbox:
            seen_bbox.add(key)
            step1.append(a)

    groups: dict = defaultdict(list)
    for a in step1:
        text_key = (getattr(a, "anchor_text", "") or "")[:30]
        page_key = str(getattr(a, "page_hint", "0"))
        groups[(page_key, text_key)].append(a)

    step2: list = []
    for group in groups.values():
        if len(group) == 1:
            step2.append(group[0])
            continue
        with_us = [a for a in group if "_" in (getattr(a, "anchor_text", "") or "")]
        if with_us:
            step2.append(with_us[0])
        else:
            step2.append(max(group, key=lambda a: float((getattr(a, "bbox", None) or [0, 0, 0, 0])[1])))

    pages_with_underscore: set = {
        str(getattr(a, "page_hint", "0"))
        for a in step2
        if "_" in (getattr(a, "anchor_text", "") or "")
    }
    result: list = [
        a for a in step2
        if "_" in (getattr(a, "anchor_text", "") or "")
        or str(getattr(a, "page_hint", "0")) not in pages_with_underscore
    ]
    return result


def _anchor_to_dict(a: SimpleNamespace) -> dict:
    return {
        "id": a.id,
        "anchor_level": a.anchor_level,
        "anchor_text": a.anchor_text,
        "position": a.position,
        "generated_pattern": a.generated_pattern,
        "bbox": list(a.bbox),
        "added_by": a.added_by,
        "page_hint": str(a.page_hint),
    }


def _reset_pipeline():
    for k in [
        "auto_doc", "auto_doc_name",
        "auto_language", "auto_signed_pdf", "all_anchors",
        "current_page", "auto_analyze_result", "auto_our_side",
        "matcher_result", "traffic_light", "run_full_pipeline",
        "apply_template_confirmed", "applied_template_id",
        "auto_patterns", "auto_matches", "fingerprint",
        "debug_prompt_step3", "debug_raw_step3",
        "debug_prompt_step4", "debug_raw_step4",
        "_last_click", "sig_scale_slider", "_sig_png_cache",
    ]:
        st.session_state.pop(k, None)
    for k in list(st.session_state.keys()):
        if k.startswith("anchor_enabled_") or k.startswith("cb_") or k.startswith("del_"):
            st.session_state.pop(k, None)


def _get_anchor_page_idx(anchor, total_pages: int):
    hint = str(anchor.page_hint)
    if hint == "first":
        return 0
    if hint == "last":
        return total_pages - 1
    if hint.isdigit():
        return int(hint)
    return None


def _anchors_for_page(anchors: list, page_idx: int, total_pages: int) -> list:
    return [
        a for a in anchors
        if (lambda pi: pi is None or pi == page_idx)(_get_anchor_page_idx(a, total_pages))
    ]


def _build_signed_pdf(signature_scale: float = 1.0) -> bytes:
    import httpx
    client = get_api_client()
    doc = st.session_state["auto_doc"]
    total = len(doc.pages)
    all_anchors = st.session_state.get("all_anchors", [])

    enabled = []
    for a in all_anchors:
        if not st.session_state.get(f"anchor_enabled_{a.id}", True):
            continue
        d = _anchor_to_dict(a)
        if _get_anchor_page_idx(a, total) is None:
            d["page_hint"] = "0"
        enabled.append(d)

    # Берём detected_signer_id из результата analyze (Модель Б — авто-выбор профиля)
    analyze_result = st.session_state.get("auto_analyze_result") or {}
    signer_id = analyze_result.get("detected_signer_id") or "default"

    def _do_sign():
        return client.sign(doc.pdf_bytes, enabled, signer_id=signer_id,
                           filename=st.session_state.get("auto_doc_name", "document.pdf"),
                           signature_scale=signature_scale)
    try:
        return _do_sign()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            local_sig = st.session_state.get("signature_png")
            if local_sig and client.upload_signature_png(signer_id, local_sig):
                return _do_sign()
            raise RuntimeError(f"Подпись для '{signer_id}' не найдена в API. Загрузите PNG в Настройки → Подписант.")
        raise


def _save_template():
    try:
        client = get_api_client()
        lang = st.session_state.get("auto_language", "ru")
        analyze_result = st.session_state.get("auto_analyze_result", {})
        our_side = analyze_result.get("our_side") or {}
        all_anchors = st.session_state.get("all_anchors", [])
        # v1.18.2 FIX: в шаблон попадают только включённые якоря. Снятая галочка
        # (anchor_enabled_*) раньше игнорировалась при сохранении — отключённое
        # место подписи возвращалось при повторной загрузке документа.
        enabled_anchors = [
            a for a in all_anchors
            if st.session_state.get(f"anchor_enabled_{a.id}", True)
        ]
        has_manual = any(a.added_by == "manual_click" for a in enabled_anchors)

        template_name = (st.session_state.get("template_name_input") or "").strip()
        if not template_name:
            template_name = _build_template_name(our_side, lang)

        fp_dict = analyze_result.get("fingerprint") or {}
        if not fp_dict:
            sys.stderr.write("[auto_sign] WARNING: fingerprint отсутствует в ответе API\n")

        tid = uuid4().hex
        returned_id = client.create_template({
            "template_id": tid,
            "name": template_name,
            "language": lang,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "manual_enrichment" if has_manual else "pipeline_auto_1",
            "fingerprint": fp_dict,
            "anchors": [_anchor_to_dict(a) for a in enabled_anchors],
            "synonyms_used": {
                "legal_entity": our_side.get("legal_entity", ""),
                "roles": our_side.get("roles", []),
                "signer": our_side.get("signer", ""),
            },
            "signature_scale": st.session_state.get("sig_scale_slider", 1.0),
        })
        st.success(t("ok_tpl_saved", name=template_name, id=(returned_id or tid)[:8]))
    except Exception as e:
        st.error(t("err_tpl_save", err=e))
        sys.stderr.write(f"[auto_sign] _save_template: {e}\n")


def _render_review(review: dict | None) -> None:
    """Отрисовать второй светофор (ревью договора). Информационно, не блокирует."""
    if not review:
        return

    tl = review.get("traffic_light", "yellow")
    err = review.get("error")

    # Заголовок секции
    st.divider()
    st.subheader(t("review_section"))

    if err:
        st.warning(t("review_error", err=err))
        return

    # Светофор ревью
    tl_label = {
        "green":  t("review_tl_green"),
        "yellow": t("review_tl_yellow"),
        "red":    t("review_tl_red"),
    }.get(tl, t("review_tl_yellow"))

    if tl == "green":
        st.success(tl_label)
    elif tl == "red":
        st.error(tl_label)
    else:
        st.warning(tl_label)

    # Заключение
    summary = review.get("summary", "")
    if summary:
        st.caption(f"{t('review_summary')} {summary}")

    if review.get("truncated"):
        st.caption(t("review_truncated"))

    # Замечания
    findings = review.get("findings", [])
    if not findings:
        st.caption(t("review_no_findings"))
        return

    axis_label = {
        "parties": t("axis_parties"), "subject": t("axis_subject"),
        "term": t("axis_term"), "payment": t("axis_payment"),
        "liability": t("axis_liability"), "signatures": t("axis_signatures"),
        "contradiction": t("axis_contradiction"), "other": t("axis_other"),
    }
    sev_icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}

    for f in findings:
        axis = axis_label.get(f.get("axis", "other"), f.get("axis", ""))
        sev = f.get("severity", "info")
        icon = sev_icon.get(sev, "ℹ️")
        note = f.get("note", "")
        clause = f.get("clause")
        clause_txt = f" ({t('review_clause')} {clause})" if clause else ""
        st.markdown(f"{icon} **{axis}**{clause_txt}: {note}")


def _render_debug_export_block() -> None:
    if not st.session_state.get("auto_doc"):
        return
    with st.expander(t("dbg_export"), expanded=False):
        analyze_result = st.session_state.get("auto_analyze_result", {})
        doc = st.session_state.get("auto_doc")
        anchors_now = st.session_state.get("all_anchors", [])
        try:
            from core.debug_export import build_debug_export
            export_data = build_debug_export(st.session_state)
        except Exception as e:
            export_data = {"analyze_result": analyze_result,
                           "all_anchors": [_anchor_to_dict(a) for a in anchors_now],
                           "_note": f"build_debug_export: {e}"}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Страниц", len(doc.pages) if doc else 0)
        c2.metric("Светофор", analyze_result.get("traffic_light") or "—")
        c3.metric("Якорей API", len(analyze_result.get("anchors", [])))
        c4.metric("Якорей сейчас", len(anchors_now))
        if analyze_result.get("error"):
            st.warning(f"API ошибка: {analyze_result['error']}")
        try:
            json_str = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            st.error(f"Сериализация: {e}")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = re.sub(r"[^A-Za-z0-9_-]", "_",
                      st.session_state.get("auto_doc_name", "doc").rsplit(".", 1)[0])[:60] or "doc"
        st.download_button(t("dbg_download"), data=json_str.encode("utf-8"),
                           file_name=f"signfinder_debug_{base}_{ts}.json",
                           mime="application/json", key="dl_debug",
                           type="primary", use_container_width=True)
        st.toggle(t("dbg_show_text"), key="dbg_show_text")
        if st.session_state.get("dbg_show_text"):
            st.caption(t("dbg_size", kb=f"{len(json_str.encode()) / 1024:.1f}"))
            st.code(json_str, language="json")


# ══════════════════════════════════════════════════════════════════════════════
# ПРЕДЗАГРУЗКА ИЗ «ПАКЕТА»
# ══════════════════════════════════════════════════════════════════════════════
def _ingest_pending_from_batch():
    pending = st.session_state.pop("razbor_pending", None)
    if not pending:
        return
    _reset_pipeline()
    from core.parser import parse_document, parse_pdf_bytes
    try:
        file_bytes = pending["pdf_bytes"]
        fname = pending["filename"]
        if file_bytes[:4] == b"%PDF":
            doc = parse_pdf_bytes(file_bytes, fname)
        else:
            doc = parse_document(file_bytes, fname)
    except Exception as e:
        st.error(f"Парсинг дока из пакета: {e}")
        return
    st.session_state["auto_doc"] = doc
    st.session_state["auto_doc_name"] = pending["filename"]
    st.session_state["auto_language"] = pending.get("language") or "ru"
    result = pending["analysis"]
    st.session_state["auto_analyze_result"] = result
    anchors = _dedup_anchors([_make_anchor(a) for a in (result.get("anchors") or [])])
    st.session_state["all_anchors"] = anchors
    st.session_state["current_page"] = _default_page_idx(len(doc.pages))
    mt = result.get("matched_template") or {}
    st.session_state["matcher_result"] = {
        "ran": True, "traffic_light": mt.get("traffic_light", result.get("traffic_light")),
        "best_match_template_id": mt.get("best_match_template_id"),
        "best_match_score": mt.get("best_match_score"),
        "candidates_count": mt.get("candidates_count", 0),
    }
    st.session_state["fingerprint"] = result.get("fingerprint")
    st.session_state["auto_our_side"] = result.get("our_side")
    st.session_state["traffic_light"] = result.get("traffic_light")
    if mt.get("traffic_light") == "green" and mt.get("best_match_template_id"):
        try:
            tpl_data = get_api_client().get_template(mt["best_match_template_id"])
            st.session_state["sig_scale_slider"] = float(tpl_data.get("signature_scale", 1.0) or 1.0)
            st.session_state["applied_template_name"] = tpl_data.get("name", "")
        except Exception as _e:
            sys.stderr.write(f"[auto_sign] batch green scale fetch: {_e}\n")


st.title(t("review_title"))
_ingest_pending_from_batch()
st.caption(t("review_caption"))


if st.session_state.get("auto_doc_name"):
    col_fname, col_new = st.columns([5, 2])
    with col_fname:
        st.caption(f"{t('lbl_current_doc')} **{st.session_state['auto_doc_name']}**")
    with col_new:
        if st.button(t("btn_new_doc"), key="btn_new_doc", use_container_width=True):
            _reset_pipeline()
            st.session_state["upload_counter"] += 1
            st.session_state["_trigger_upload"] = True
            st.rerun()

uploader_key = f"auto_uploader_{st.session_state['upload_counter']}"
_doc_loaded = bool(st.session_state.get("auto_doc_name"))
if st.session_state.pop("_trigger_upload", False):
    _components.html(
        "<script>"
        "window.parent.document.querySelectorAll('input[type=\"file\"]')[0]?.click();"
        "</script>",
        height=0,
    )
uploaded = st.file_uploader(
    t("uploader_label"), type=["pdf", "docx"], key=uploader_key,
    disabled=_doc_loaded,
    label_visibility="collapsed" if _doc_loaded else "visible",
)

with_review = st.toggle(
    t("review_toggle"),
    help=t("review_toggle_help"),
    key="with_review",
)

if uploaded is not None and st.session_state.get("auto_doc_name") != uploaded.name:
    _reset_pipeline()
    st.session_state["auto_doc_name"] = uploaded.name

    with st.status(t("status_analyzing"), expanded=True) as status:
        parse_ok = True

        st.write(t("step_parsing"))
        from core.parser import parse_document
        try:
            doc = parse_document(uploaded.getvalue(), uploaded.name)
            st.session_state["auto_doc"] = doc
            st.write(t("step_parsed_ok", n=len(doc.pages)))
        except Exception as e:
            status.update(label=t("err_parsing"), state="error")
            st.error(str(e))
            parse_ok = False

        if parse_ok:
            st.write(t("step_language"))
            from core.language_detector import detect_language
            lang = detect_language(doc)
            if lang not in SUPPORTED_LANGUAGES:
                status.update(label=t("err_lang_unsupported"), state="error")
                st.error(t("err_lang_detail", lang=lang or "?"))
                parse_ok = False
            else:
                st.session_state["auto_language"] = lang
                st.write(t("step_lang_ok", lang=lang))

        if parse_ok:
            st.write(t("step_analysis"))
            try:
                client = get_api_client()
                result = client.analyze(
                    doc.pdf_bytes, language=lang, filename=uploaded.name,
                    with_review=with_review,
                )
                st.session_state["auto_analyze_result"] = result

                tl = result.get("traffic_light", "no_match")

                if tl == "no_match":
                    status.update(label=t("err_doc_failed"), state="error")
                    st.error(t("err_doc_detail", err=result.get('error', 'неизвестная ошибка')))
                    st.stop()

                anchors = [_make_anchor(a) for a in (result.get("anchors") or [])]
                anchors = _dedup_anchors(anchors)
                st.session_state["all_anchors"] = anchors
                st.session_state["current_page"] = _default_page_idx(len(doc.pages))

                mt = result.get("matched_template") or {}
                st.session_state["matcher_result"] = {
                    "ran": True,
                    "traffic_light": mt.get("traffic_light", tl),
                    "best_match_template_id": mt.get("best_match_template_id"),
                    "best_match_score": mt.get("best_match_score"),
                    "candidates_count": mt.get("candidates_count", 0),
                }
                st.session_state["fingerprint"] = result.get("fingerprint")
                st.session_state["auto_our_side"] = result.get("our_side")
                st.session_state["traffic_light"] = tl

                # Загружаем подпись нужного подписанта для превью
                detected_signer = result.get("detected_signer_id") or "default"
                try:
                    sig_png = get_api_client().get_signature_png(detected_signer)
                    if sig_png:
                        st.session_state["signature_png"] = sig_png
                except Exception as _e:
                    sys.stderr.write(f"[auto_sign] load sig for {detected_signer}: {_e}\n")

                if tl == "green" and mt.get("best_match_template_id"):
                    pct = int((mt.get("best_match_score") or 0) * 100)
                    try:
                        tpl_data = client.get_template(mt["best_match_template_id"])
                        st.session_state["sig_scale_slider"] = float(tpl_data.get("signature_scale", 1.0) or 1.0)
                        st.session_state["applied_template_name"] = tpl_data.get("name", "")
                        tpl_display = tpl_data.get("name") or mt['best_match_template_id'][:8] + "…"
                    except Exception as _e:
                        sys.stderr.write(f"[auto_sign] green scale fetch: {_e}\n")
                        tpl_display = mt['best_match_template_id'][:8] + "…"
                    st.write(t("step_green", name=tpl_display, pct=pct, n=len(anchors)))
                elif anchors:
                    st.write(t("step_yellow", n=len(anchors)))
                else:
                    st.write(t("step_no_anchors"))

                if result.get("error"):
                    st.warning(t("warn_api", msg=result['error']))

                status.update(label=t("status_done"), state="complete")

            except Exception as e:
                status.update(label=t("status_err_analysis"), state="error")
                st.error(t("err_analyze_api", err=e))
                sys.stderr.write(f"[auto_sign] client.analyze: {e}\n")


if "auto_analyze_result" in st.session_state and "all_anchors" in st.session_state:
    ar = st.session_state["auto_analyze_result"]
    tl = ar.get("traffic_light", "no_match")
    mt = ar.get("matched_template") or {}
    our_side = ar.get("our_side") or {}

    if tl == "green" and mt.get("best_match_template_id"):
        pct = int((mt.get("best_match_score") or 0) * 100)
        tpl_display = st.session_state.get("applied_template_name") or mt['best_match_template_id'][:8] + "…"
        with st.container(border=True):
            st.success(t("banner_green", name=tpl_display, pct=pct))
    else:
        entity = our_side.get("legal_entity", "")
        signer_name = our_side.get("signer", "")
        with st.container(border=True):
            if entity:
                st.warning(t("banner_yellow_side", entity=entity, signer=signer_name))
            else:
                st.info(t("banner_yellow_no_tpl"))
        if st.button(t("btn_reanalyze"), key="btn_reanalyze"):
            _reset_pipeline()
            st.session_state["upload_counter"] += 1
            st.rerun()

    _render_review(ar.get("review"))

_render_debug_export_block()

if "all_anchors" not in st.session_state:
    st.stop()

doc = st.session_state["auto_doc"]
total_pages = len(doc.pages)
all_anchors: list = st.session_state["all_anchors"]
current_page: int = st.session_state.get("current_page", 0)

st.divider()
st.subheader(t("section_preview"))

# Масштаб подписи — единый на весь документ. Слайдер ВЫШЕ превью, чтобы его
# значение применялось к превью сразу (на всех страницах одинаково).
# Дефолт через session_state (не value=), чтобы зелёный путь подставил масштаб
# из шаблона до создания виджета.
if "sig_scale_slider" not in st.session_state:
    st.session_state["sig_scale_slider"] = 1.0
sig_scale = st.slider(
    t("slider_scale"),
    min_value=0.5, max_value=3.0, step=0.1,
    format="%.1f×",
    help=t("slider_scale_help"),
    key="sig_scale_slider",
)

page_anchors = _anchors_for_page(all_anchors, current_page, total_pages)

if page_anchors:
    st.write(t("lbl_anchors_on_page", n=current_page + 1))
    ca, cn, _ = st.columns([1, 1, 4])
    with ca:
        if st.button(t("btn_all_on"), key="en_all"):
            for a in page_anchors:
                st.session_state[f"anchor_enabled_{a.id}"] = True
            st.rerun()
    with cn:
        if st.button(t("btn_all_off"), key="dis_all"):
            for a in page_anchors:
                st.session_state[f"anchor_enabled_{a.id}"] = False
            st.rerun()

    for i, anchor in enumerate(page_anchors):
        c1, c2, c3 = st.columns([1, 9, 1])
        with c1:
            enabled = st.checkbox("", value=st.session_state.get(f"anchor_enabled_{anchor.id}", True),
                                  key=f"cb_{anchor.id}")
            st.session_state[f"anchor_enabled_{anchor.id}"] = enabled
        with c2:
            src = "auto" if anchor.added_by == "auto_regex" else "✏️ manual"
            st.caption(f"#{i+1} {src} · Ур.{anchor.anchor_level} · «{anchor.anchor_text[:40]}»")
        with c3:
            if st.button("✕", key=f"del_{anchor.id}"):
                st.session_state["all_anchors"] = [a for a in all_anchors if a.id != anchor.id]
                st.rerun()
else:
    st.caption(t("lbl_no_anchors_page", n=current_page + 1))

canvas_mode_label = st.radio(t("radio_canvas_mode"),
                              [t("mode_view"), t("mode_add")],
                              horizontal=True, key="canvas_mode_radio")
mode_key = "add" if t("mode_add") in canvas_mode_label else "view"

nav1, nav2, nav3, nav4 = st.columns([1, 2, 2, 1])
with nav1:
    if st.button("◀", key="pg_prev", disabled=(current_page == 0)):
        st.session_state["current_page"] = max(0, current_page - 1)
        st.rerun()
with nav2:
    st.markdown(t("lbl_page", cur=current_page + 1, total=total_pages))
with nav3:
    jump = st.number_input(t("lbl_jump_to"), min_value=1, max_value=total_pages,
                           value=current_page + 1, label_visibility="collapsed",
                           key=f"pg_jump_{current_page}")
    if jump - 1 != current_page:
        st.session_state["current_page"] = jump - 1
        st.rerun()
with nav4:
    if st.button("▶", key="pg_next", disabled=(current_page >= total_pages - 1)):
        st.session_state["current_page"] = min(total_pages - 1, current_page + 1)
        st.rerun()

_preview_rendered = False
try:
    from core.preview import render_page_with_highlights
    pm = []
    for a in page_anchors:
        pi = _get_anchor_page_idx(a, total_pages)
        if pi is None or pi == current_page:
            pm.append(SimpleNamespace(
                id=a.id, page=current_page, bbox=a.bbox,
                context=a.anchor_text, party="", pattern=a.generated_pattern,
                confidence=1.0, status="candidate",
                operator_excluded=not st.session_state.get(f"anchor_enabled_{a.id}", True),
            ))

    # Получить режим подписания для превью
    try:
        _mode_r = requests.get(f"{API_BASE}/v1/settings/sign-mode",
                               headers=get_api_client()._headers, timeout=3)
        _mode = _mode_r.json() if _mode_r.ok else {}
    except Exception:
        _mode = {}

    # Подпись для превью — по детектированному подписанту ТЕКУЩЕГО документа,
    # не из устаревшего session-глобала (иначе разные доки = одна подпись).
    sig_png = _signature_for_current_doc() if _mode.get("use_signature", True) else None
    # sig_scale определён выше (слайдер над превью) — применяется немедленно
    img_bytes = render_page_with_highlights(
        doc.pdf_bytes, current_page, pm,
        scale=1.5, signature_png=sig_png, sig_scale=sig_scale,
        use_marker=_mode.get("use_marker", False),
        marker_color=_mode.get("marker_color", "pink"),
    )

    if mode_key == "add":
        from streamlit_image_coordinates import streamlit_image_coordinates
        from PIL import Image
        coords = streamlit_image_coordinates(Image.open(io.BytesIO(img_bytes)),
                                             key=f"click_{current_page}_{len(page_anchors)}")
        if coords is not None:
            scale = 1.5
            cx, cy = coords["x"] / scale, coords["y"] / scale
            this_click = (current_page, round(cx, 1), round(cy, 1))
            if st.session_state.get("_last_click") != this_click:
                st.session_state["_last_click"] = this_click
                try:
                    new_d = get_api_client().build_anchor_from_click(
                        doc.pdf_bytes, current_page, cx, cy,
                        st.session_state.get("auto_language", "ru"),
                        filename=st.session_state.get("auto_doc_name", "document.pdf"),
                    )
                    if new_d:
                        sw, sh = 150.0, 12.0
                        new_d["bbox"] = [cx - sw/2, cy - sh/2, cx + sw/2, cy + sh/2]
                        st.session_state["all_anchors"].append(_make_anchor(new_d))
                        st.rerun()
                    else:
                        st.warning(t("warn_no_text"))
                except Exception as e:
                    st.error(t("err_anchor_add", err=e))
    else:
        st.image(img_bytes, use_container_width=True)
    _preview_rendered = True
except Exception as e:
    st.warning(t("warn_preview", err=e))

if mode_key == "add" and not _preview_rendered:
    st.caption(t("lbl_manual_coords"))
    mx_col, my_col, madd_col = st.columns([2, 2, 1])
    with mx_col:
        mx = st.number_input("X (pt)", min_value=0.0, value=100.0, key="man_x")
    with my_col:
        my = st.number_input("Y (pt)", min_value=0.0, value=200.0, key="man_y")
    with madd_col:
        st.write(""); st.write("")
        if st.button("➕", key="btn_add_manual"):
            try:
                a_d = get_api_client().build_anchor_from_click(
                    doc.pdf_bytes, current_page, mx, my,
                    st.session_state.get("auto_language", "ru"),
                    filename=st.session_state.get("auto_doc_name", "document.pdf"),
                )
                if a_d:
                    sw, sh = 150.0, 12.0
                    a_d["bbox"] = [mx - sw/2, my - sh/2, mx + sw/2, my + sh/2]
                    st.session_state["all_anchors"].append(_make_anchor(a_d))
                    st.rerun()
                else:
                    st.warning(t("warn_no_text"))
            except Exception as e:
                st.error(str(e))

st.divider()
st.subheader(t("section_download"))

auto_n = sum(1 for a in all_anchors if a.added_by == "auto_regex")
manual_n = sum(1 for a in all_anchors if a.added_by == "manual_click")
enabled_n = sum(1 for a in all_anchors if st.session_state.get(f"anchor_enabled_{a.id}", True))
st.caption(t("caption_anchors_stat", auto=auto_n, manual=manual_n, total=len(all_anchors), enabled=enabled_n))

if enabled_n == 0:
    st.warning(t("warn_no_enabled"))
else:
    st.caption(t("caption_scale", scale=f"{sig_scale:.1f}"))
    if st.button(t("btn_sign_download"), type="primary", key="btn_sign"):
        try:
            st.session_state["auto_signed_pdf"] = _build_signed_pdf(signature_scale=sig_scale)
        except Exception as e:
            st.error(t("err_signing", err=e))
    if "auto_signed_pdf" in st.session_state:
        fname = st.session_state.get("auto_doc_name", "doc").rsplit(".", 1)[0]
        st.download_button(t("btn_save_pdf"), data=st.session_state["auto_signed_pdf"],
                           file_name=f"{fname}_signed.pdf", mime="application/pdf", key="dl_signed")

st.divider()
st.subheader(t("section_save_tpl"))

has_manual = any(a.added_by == "manual_click" for a in all_anchors)
lang_h = st.session_state.get("auto_language", "ru")
ar_now = st.session_state.get("auto_analyze_result", {})

try:
    _tl_now = ar_now.get("traffic_light", "")
    _applied_name = st.session_state.get("applied_template_name", "")
    if _tl_now == "green" and _applied_name:
        def_name = _applied_name
    else:
        def_name = _build_template_name(ar_now.get("our_side") or {}, lang_h)
except Exception:
    from datetime import date
    def_name = f"Договор {lang_h} ({date.today().strftime('%d.%m.%Y')})"

st.text_input(t("lbl_tpl_name"), value=def_name, key="template_name_input")
_lbl = t("btn_save_tpl_manual") if has_manual else t("btn_save_tpl")

applied_tid = ar_now.get("applied_template_id")
if applied_tid and has_manual:
    st.info(t("info_tpl_manual"))
    vc1, vc2, vc3 = st.columns(3)
    with vc1:
        if st.button(t("btn_update_tpl"), key="btn_upd_tpl"):
            try:
                from core.template_storage import add_anchors_to_template
                manual_dicts = [_anchor_to_dict(a) for a in all_anchors if a.added_by == "manual_click"]
                add_anchors_to_template(applied_tid, manual_dicts, increment_version=False)
                st.success(t("ok_tpl_updated"))
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with vc2:
        if st.button(t("btn_new_version"), key="btn_new_ver"):
            try:
                from core.template_storage import add_anchors_to_template
                manual_dicts = [_anchor_to_dict(a) for a in all_anchors if a.added_by == "manual_click"]
                new_id = add_anchors_to_template(applied_tid, manual_dicts, increment_version=True)
                st.success(t("ok_tpl_new_ver", id=new_id[:8]))
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with vc3:
        if st.button(t("btn_no_save"), key="btn_no_save_ver"):
            ar_now.pop("applied_template_id", None)
            st.rerun()

if st.button(_lbl, type="primary" if has_manual else "secondary", key="btn_save_tpl"):
    _save_template()

st.caption(f"SignFinder v{_sf_version()}")
