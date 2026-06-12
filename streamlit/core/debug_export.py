"""Сборка полного диагностического JSON для страницы Авто-подписания.

Назначение: собрать ВСЁ что нужно для диагностики регрессии v1.6→v1.7→v1.8→v1.9.

v1.9 FIX:
  - _build_matcher: понимает И MatcherResult объект, И dict (как кладёт страница после
    миграции на API). Раньше падал на AttributeError → matcher.ran: false.
  - _build_fingerprint: понимает И dict от API, И dataclass.
  - load_template/parties.json через API — нет endpoint, секции возвращают
    "endpoint not available in v1.9".
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any


def _safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe(v) for k, v in obj.items()}
    if is_dataclass(obj):
        try:
            return _safe(asdict(obj))
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return _safe({k: v for k, v in vars(obj).items() if not k.startswith("_")})
        except Exception:
            pass
    try:
        return str(obj)
    except Exception:
        return f"<unserializable {type(obj).__name__}>"


def _section(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper


def _get(obj, key, default=None):
    """Универсальный getter: работает и для dict и для объекта с атрибутами."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@_section
def _build_doc_info(ss: dict) -> dict:
    doc = ss.get("auto_doc")
    return {
        "filename": ss.get("auto_doc_name", ""),
        "pages": len(doc.pages) if doc else 0,
        "language": ss.get("auto_language", ""),
        "pdf_bytes_size": len(doc.pdf_bytes) if doc and hasattr(doc, "pdf_bytes") else None,
    }


@_section
def _build_fingerprint(ss: dict) -> dict:
    fp = ss.get("fingerprint")
    if fp is None:
        return {"present": False}
    safe_fp = _safe(fp)
    if isinstance(safe_fp, dict):
        return {"present": True, **safe_fp}
    return {"present": True, "value": safe_fp}


@_section
def _build_matcher(ss: dict) -> dict:
    """Принимает И MatcherResult объект, И dict от API."""
    mr = ss.get("matcher_result")
    if mr is None:
        return {"ran": False}

    # API-вариант: dict с явным ran=True
    if isinstance(mr, dict) and "ran" in mr:
        return {
            "ran": bool(mr.get("ran")),
            "traffic_light": mr.get("traffic_light"),
            "best_match_template_id": mr.get("best_match_template_id"),
            "best_match_score": mr.get("best_match_score"),
            "candidates_count": mr.get("candidates_count", 0),
            "source": "api_dict",
        }

    # Legacy: MatcherResult объект
    candidates = _get(mr, "all_candidates", []) or []
    best = _get(mr, "best_match")
    result = {
        "ran": True,
        "traffic_light": _get(mr, "traffic_light"),
        "internal_score": _get(mr, "internal_score"),
        "best_match": _safe(best) if best is not None else None,
        "all_candidates_count": len(candidates),
        "all_candidates": [_safe(c) for c in candidates],
        "explanation": _get(mr, "explanation"),
        "source": "legacy_object",
    }
    return result


@_section
def _build_applied_template(ss: dict) -> dict:
    tid = ss.get("applied_template_id")
    if not tid:
        return {"applied": False}
    # v1.9: load_template из core упал бы (нет parties.json/локального хранилища)
    # API имеет GET /v1/templates/{id} но debug_export не делает HTTP-вызовы
    return {
        "applied": True,
        "template_id": tid,
        "note": "v1.9: полные данные шаблона см. в API GET /v1/templates/{id}",
    }


@_section
def _build_pipeline(ss: dict) -> dict:
    has_step3 = bool(ss.get("debug_prompt_step3") or ss.get("auto_our_side"))
    has_step4 = bool(ss.get("debug_prompt_step4") or ss.get("auto_patterns"))
    has_step5 = bool(ss.get("auto_matches"))

    if not (has_step3 or has_step4 or has_step5):
        return {"ran": False, "reason": "template applied or pipeline data not in session"}

    our_side = ss.get("auto_our_side") or {}
    patterns = ss.get("auto_patterns") or []
    matches = ss.get("auto_matches") or []

    return {
        "ran": True,
        "step3": {
            "legal_entity": our_side.get("legal_entity", ""),
            "roles": our_side.get("roles", []),
            "signer": our_side.get("signer", ""),
            "confidence": our_side.get("confidence", 0),
            "match_reason": our_side.get("match_reason", ""),
            "evidence": our_side.get("evidence", ""),
            "all_parties": our_side.get("all_parties", []),
            "prompt": ss.get("debug_prompt_step3", ""),
            "raw_llm_response": ss.get("debug_raw_step3", ""),
        },
        "step4": {
            "patterns_count": len(patterns),
            "patterns": list(patterns),
            "prompt": ss.get("debug_prompt_step4", ""),
            "raw_llm_response": ss.get("debug_raw_step4", ""),
        },
        "step5": {
            "matches_count": len(matches),
            "matches": [
                {
                    "id": _get(m, "id"),
                    "page": _get(m, "page"),
                    "bbox": list(_get(m, "bbox", []) or []),
                    "context": _get(m, "context"),
                    "party": _get(m, "party"),
                    "pattern": _get(m, "pattern"),
                    "confidence": _get(m, "confidence"),
                    "status": _get(m, "status"),
                }
                for m in matches
            ],
        },
    }


@_section
def _build_anchors(ss: dict) -> dict:
    anchors = ss.get("all_anchors") or []
    items = []
    for a in anchors:
        safe = _safe(a)
        if isinstance(safe, dict):
            safe["enabled_in_session"] = ss.get(f"anchor_enabled_{_get(a, 'id', '')}", True)
        items.append(safe)

    by_source = {"auto_regex": 0, "manual_click": 0, "other": 0}
    for a in anchors:
        src = _get(a, "added_by") or "other"
        by_source[src] = by_source.get(src, 0) + 1

    return {"total": len(anchors), "by_source": by_source, "anchors": items}


def _bbox_center(bbox) -> tuple:
    try:
        if not bbox or len(bbox) < 4:
            return None
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    except Exception:
        return None


def _anchor_page_int(anchor) -> int:
    ph = _get(anchor, "page_hint")
    if ph is None:
        return -1
    s = str(ph)
    return int(s) if s.isdigit() else -1


@_section
def _build_matches_to_anchors_mapping(ss: dict) -> dict:
    BBOX_TOLERANCE_PT = 3.0
    matches = ss.get("auto_matches") or []
    anchors = ss.get("all_anchors") or []

    from collections import defaultdict
    anchors_by_page = defaultdict(list)
    for a in anchors:
        anchors_by_page[_anchor_page_int(a)].append(a)

    mapping = []
    matched_anchor_ids = set()
    for m in matches:
        m_page = _get(m, "page", -1)
        m_bbox = list(_get(m, "bbox", []) or [])
        m_center = _bbox_center(m_bbox)
        found = None
        if m_center is not None:
            for a in anchors_by_page.get(m_page, []):
                a_center = _bbox_center(_get(a, "bbox", []))
                if a_center is None:
                    continue
                if (abs(a_center[0] - m_center[0]) <= BBOX_TOLERANCE_PT and
                        abs(a_center[1] - m_center[1]) <= BBOX_TOLERANCE_PT):
                    found = a
                    break
        if found is not None:
            matched_anchor_ids.add(_get(found, "id"))
        mapping.append({
            "match_id": _get(m, "id"),
            "match_page": m_page,
            "match_pattern": _get(m, "pattern"),
            "anchor_found": found is not None,
            "anchor_id": _get(found, "id") if found else None,
            "anchor_added_by": _get(found, "added_by") if found else None,
        })

    orphan = [
        {
            "anchor_id": _get(a, "id"),
            "added_by": _get(a, "added_by"),
            "anchor_text": _get(a, "anchor_text"),
            "generated_pattern": _get(a, "generated_pattern"),
            "page_hint": str(_get(a, "page_hint", "")),
        }
        for a in anchors if _get(a, "id") not in matched_anchor_ids
    ]

    return {
        "matches_count": len(matches),
        "anchors_count": len(anchors),
        "matched_pairs_count": len([x for x in mapping if x["anchor_found"]]),
        "lost_matches_count": len([x for x in mapping if not x["anchor_found"]]),
        "orphan_anchors_count": len(orphan),
        "mapping_method": "by_position (page + bbox center)",
        "bbox_tolerance_pt": BBOX_TOLERANCE_PT,
        "mapping": mapping,
        "orphan_anchors": orphan,
    }


@_section
def _build_parties_section(ss: dict) -> dict:
    # v1.9: parties через API GET /v1/parties. debug_export не делает HTTP.
    return {
        "present": False,
        "reason": "v1.9: parties перенесены в API, см. GET /v1/parties",
    }


@_section
def _build_session_flags(ss: dict) -> dict:
    return {
        "run_full_pipeline": ss.get("run_full_pipeline"),
        "apply_template_confirmed": ss.get("apply_template_confirmed"),
        "applied_template_id": ss.get("applied_template_id"),
        "traffic_light": ss.get("traffic_light"),
        "current_page": ss.get("current_page"),
    }


def build_debug_export(session_state) -> dict:
    ss = {}
    try:
        for k in session_state:
            ss[k] = session_state[k]
    except Exception:
        ss = dict(session_state) if hasattr(session_state, "items") else {}

    return {
        "export_version": "1.9-debug",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "doc_info": _build_doc_info(ss),
        "session_flags": _build_session_flags(ss),
        "fingerprint": _build_fingerprint(ss),
        "matcher": _build_matcher(ss),
        "applied_template": _build_applied_template(ss),
        "pipeline": _build_pipeline(ss),
        "matches_to_anchors_mapping": _build_matches_to_anchors_mapping(ss),
        "all_anchors": _build_anchors(ss),
        "parties_json": _build_parties_section(ss),
        # v1.9: bonus — raw результат API analyze для отладки
        "api_analyze_raw": ss.get("auto_analyze_result"),
    }
