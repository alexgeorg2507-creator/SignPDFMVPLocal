"""Страница настроек SignFinder v1.18.5."""
import json
import os

import requests
import streamlit as st


if not st.session_state.get("auth"):
    st.warning("Войдите через главную страницу.")
    st.stop()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.api_client import get_api_client

st.title("⚙️ Настройки SignFinder")

LANGUAGES = ["ru", "en", "pl", "mk"]
API_BASE = os.environ.get("API_URL", "http://api:8000")


@st.cache_data(ttl=60)
def _sf_version() -> str:
    try:
        r = requests.get(f"{API_BASE}/v1/version", timeout=3)
        return r.json().get("api_version", "?")
    except Exception:
        return "?"


def _api_headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('SIGNFINDER_API_KEY', '')}"}


@st.cache_data(ttl=10)
def _fetch_templates(lang_filter: str = "", status_filter: str = "") -> list:
    params: dict = {}
    if lang_filter:
        params["language"] = lang_filter
    if status_filter:
        params["status"] = status_filter
    r = requests.get(f"{API_BASE}/v1/templates", params=params,
                     headers=_api_headers(), timeout=5)
    r.raise_for_status()
    return r.json().get("templates", [])


_MAIL_DEF: dict = {
    "imap_host": "", "imap_port": 993, "imap_user": "", "imap_password": "",
    "imap_ssl": True, "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": "",
    "poll_interval_sec": 300, "reply_to_sender": False,
    "folder_in": "SignfinderIn", "folder_green": "SignfinderGreen",
    "folder_yellow": "SignfinderYellow", "folder_red": "SignfinderRed",
    "folder_archive": "SignfinderArchive",
    "auth_method": "basic",
    "oauth2_provider": "google",
    "oauth2_client_id": "",
    "oauth2_client_secret": "",
    "oauth2_refresh_token": "",
    "oauth2_token_endpoint": "",
}

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


def _load_mail_cfg() -> dict:
    if "_mail_cfg" not in st.session_state:
        try:
            r = requests.get(f"{API_BASE}/v1/settings/mail-config",
                             headers=_api_headers(), timeout=5)
            st.session_state["_mail_cfg"] = r.json() if r.ok else dict(_MAIL_DEF)
        except Exception:
            st.session_state["_mail_cfg"] = dict(_MAIL_DEF)
    return st.session_state["_mail_cfg"]


_SECRET_KEYS = ("imap_password", "smtp_password", "oauth2_client_secret", "oauth2_refresh_token")


def _autosave_mail() -> None:
    saved = st.session_state.get("_mail_cfg", dict(_MAIL_DEF))
    cfg: dict = {}
    for k, default in _MAIL_DEF.items():
        val = st.session_state.get(f"mail_{k}", saved.get(k, default))
        if k in _SECRET_KEYS and not val:
            val = saved.get(k, "")
        cfg[k] = val
    try:
        r = requests.put(f"{API_BASE}/v1/settings/mail-config",
                         json=cfg, headers=_api_headers(), timeout=5)
        if r.ok:
            st.session_state["_mail_cfg"] = cfg
            st.session_state["_mail_toast"] = True
    except Exception:
        pass


def _on_provider_change() -> None:
    p = st.session_state.get("mail_oauth2_provider", "google")
    preset = _OAUTH_PRESETS.get(p, _OAUTH_PRESETS["google"])
    st.session_state["mail_imap_host"] = preset["imap_host"]
    st.session_state["mail_imap_port"] = preset["imap_port"]
    st.session_state["mail_smtp_host"] = preset["smtp_host"]
    st.session_state["mail_smtp_port"] = preset["smtp_port"]
    st.session_state["mail_oauth2_token_endpoint"] = preset["token_endpoint"]
    _autosave_mail()


tab_templates, tab_prompts, tab_signer, tab_markers, tab_llm, tab_mail, tab_test = st.tabs([
    "📋 Шаблоны",
    "🤖 Промпты",
    "👤 Подписант",
    "🔖 Маркеры",
    "🧠 LLM",
    "📧 Mail",
    "🧪 Тестирование",
])


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 0: Шаблоны
# ══════════════════════════════════════════════════════════════════════════════
with tab_templates:
    cf1, cf2, cf3, cf4 = st.columns([2, 2, 2, 2])
    lang_f = cf1.selectbox("Язык", ["все", "ru", "en", "pl"], key="tpl_lang")
    status_f = cf2.selectbox("Статус", ["все", "active", "archived", "low_quality"], key="tpl_status")
    if cf3.button("🔄 Обновить", key="tpl_reload"):
        st.cache_data.clear()
        st.rerun()
    if cf4.button("🗑 Удалить все", key="tpl_del_all"):
        st.session_state["tpl_del_all_confirm"] = True

    try:
        tpls = _fetch_templates(
            "" if lang_f == "все" else lang_f,
            "" if status_f == "все" else status_f,
        )
        tpl_error = None
    except Exception as _e:
        tpls = []
        tpl_error = str(_e)

    if tpl_error:
        st.error(f"Ошибка API: {tpl_error}")
    elif not tpls:
        st.info("Шаблонов нет.")
    else:
        h = st.columns([3, 1, 1, 1, 1, 2, 1, 1])
        for _col, _lbl in zip(h, ["**Имя**", "**Яз.**", "**Статус**", "**Якорей**",
                                    "**Применён**", "**Создан**", "", ""]):
            _col.markdown(_lbl)
        st.divider()

        for tpl in tpls:
            tid = tpl["id"]
            extra = tpl.get("extra", {})
            created_str = (extra.get("created_at") or "")[:10]

            r0, r1, r2, r3, r4, r5, r6, r7 = st.columns([3, 1, 1, 1, 1, 2, 1, 1])
            r0.write(tpl["name"])
            r1.write(tpl["language"])
            r2.write(tpl["status"])
            r3.write(str(tpl["anchor_count"]))
            r4.write(str(tpl["usage_count"]))
            r5.write(created_str)

            if r6.button("👁", key=f"tpl_v_{tid}"):
                st.session_state[f"tpl_view_{tid}"] = not st.session_state.get(f"tpl_view_{tid}", False)
            if r7.button("🗑", key=f"tpl_d_{tid}"):
                st.session_state[f"tpl_del_{tid}"] = True

            # ── Подтверждение удаления ────────────────────────────────────────
            if st.session_state.get(f"tpl_del_{tid}"):
                st.warning(f"Удалить **{tpl['name']}**? Это необратимо.")
                ca, cb = st.columns([1, 1])
                if ca.button("✅ Да, удалить", key=f"tpl_dc_{tid}", type="primary"):
                    try:
                        requests.delete(f"{API_BASE}/v1/templates/{tid}",
                                        headers=_api_headers(), timeout=5)
                        st.success("Удалено.")
                        st.cache_data.clear()
                        st.session_state.pop(f"tpl_del_{tid}", None)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Ошибка: {_e}")
                if cb.button("Отмена", key=f"tpl_dc_cancel_{tid}"):
                    st.session_state.pop(f"tpl_del_{tid}", None)
                    st.rerun()

            # ── Просмотр деталей ──────────────────────────────────────────────
            if st.session_state.get(f"tpl_view_{tid}", False):
                with st.expander(f"👁 {tpl['name']}", expanded=True):
                    vc1, vc2 = st.columns(2)
                    with vc1:
                        st.caption("**Fingerprint**")
                        fp_sh = extra.get("fingerprint_simhash", "")
                        st.code(str(fp_sh)[:48] if fp_sh else "—", language="text")
                        words = extra.get("fingerprint_words", [])
                        if words:
                            st.caption("Топ слова: " + ", ".join(str(w) for w in words[:12]))
                        st.caption(f"Создан: {extra.get('created_at', '—')}")
                        st.caption(f"Источник: {extra.get('created_by', '—')}")
                        st.json({
                            "times_applied": tpl["usage_count"],
                            "times_confirmed": extra.get("times_confirmed", 0),
                            "times_rejected": extra.get("times_rejected", 0),
                            "last_used": extra.get("last_used"),
                        })
                    with vc2:
                        st.caption("**Якоря**")
                        for anc in (extra.get("anchors") or [])[:6]:
                            if isinstance(anc, dict):
                                st.caption(
                                    f"• стр. {anc.get('page_hint', '?')}: "
                                    f"`{str(anc.get('anchor_text', ''))[:50]}`"
                                )
                            else:
                                st.caption(f"• {str(anc)[:60]}")

            st.divider()

        # Статистика внизу
        by_status: dict = {}
        for _t in tpls:
            _s = _t.get("status", "active")
            by_status[_s] = by_status.get(_s, 0) + 1
        parts = [f"Всего: {len(tpls)}"]
        parts += [f"{_s.capitalize()}: {_c}" for _s, _c in sorted(by_status.items())]
        st.caption(" · ".join(parts))

        st.divider()
        if st.session_state.get("tpl_del_all_confirm"):
            st.warning(f"Удалить все {len(tpls)} шаблонов? Это необратимо.")
            da, db = st.columns([1, 1])
            if da.button("✅ Да, удалить все", key="tpl_del_all_ok", type="primary"):
                _errors = []
                for _t in tpls:
                    try:
                        requests.delete(f"{API_BASE}/v1/templates/{_t['id']}",
                                        headers=_api_headers(), timeout=5)
                    except Exception as _e:
                        _errors.append(str(_e))
                st.session_state.pop("tpl_del_all_confirm", None)
                st.cache_data.clear()
                if _errors:
                    st.error("Некоторые не удалены: " + "; ".join(_errors))
                else:
                    st.success("Все шаблоны удалены.")
                st.rerun()
            if db.button("Отмена", key="tpl_del_all_cancel"):
                st.session_state.pop("tpl_del_all_confirm", None)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 1: Промпты
# ══════════════════════════════════════════════════════════════════════════════
with tab_prompts:
    st.caption("⏳ *Пока через core.prompts — нет endpoint в API.*")
    from core.prompts import load_prompts, save_prompts, PROMPT_META, DEFAULTS as PROMPT_DEFAULTS
    if "prompts_data" not in st.session_state:
        st.session_state["prompts_data"] = load_prompts()
    prompts_data = st.session_state["prompts_data"]
    col_p_save, col_p_reset, col_p_reload = st.columns([1, 1, 2])
    with col_p_save:
        if st.button("💾 Сохранить промпты", type="primary", key="prompts_save"):
            try:
                save_prompts(st.session_state["prompts_data"])
                st.success("✅ Сохранено")
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with col_p_reset:
        if st.button("↩ Сбросить", key="prompts_reset"):
            st.session_state["prompts_data"] = dict(PROMPT_DEFAULTS)
            try:
                save_prompts(dict(PROMPT_DEFAULTS))
                st.success("✅ Сброшено")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with col_p_reload:
        if st.button("🔄 Перечитать", key="prompts_reload"):
            st.session_state.pop("prompts_data", None)
            st.rerun()
    st.divider()
    for key, meta in PROMPT_META.items():
        with st.expander(f"**{meta['label']}** · `{meta['module']}`", expanded=False):
            st.caption(f"Влияет на: {meta['effect']}")
            current_val = prompts_data.get(key, PROMPT_DEFAULTS.get(key, ""))
            new_val = st.text_area("Текст промпта", value=current_val, height=200,
                                   key=f"prompt_{key}", label_visibility="collapsed")
            prompts_data[key] = new_val
            if current_val != PROMPT_DEFAULTS.get(key, ""):
                st.warning("⚠️ Отличается от дефолта")
            else:
                st.success("✓ Дефолт")


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 2: Подписант
# ══════════════════════════════════════════════════════════════════════════════

def _sig_html(img_bytes: bytes, width: int = 240) -> str:
    import base64 as _b64
    b64 = _b64.b64encode(img_bytes).decode()
    return (
        '<div style="background:#fff;display:inline-block;padding:8px;'
        'border-radius:6px;border:1px solid #ccc">'
        f'<img src="data:image/png;base64,{b64}" width="{width}" style="display:block"/>'
        '</div>'
    )


def _api_get_signers() -> list:
    r = requests.get(f"{API_BASE}/v1/signers", headers=_api_headers(), timeout=5)
    return r.json() if r.ok else []


def _api_get_signer(sid: str) -> dict:
    r = requests.get(f"{API_BASE}/v1/signers/{sid}", headers=_api_headers(), timeout=5)
    return r.json() if r.ok else {}


def _api_save_signer(sid: str, payload: dict) -> bool:
    r = requests.put(f"{API_BASE}/v1/signers/{sid}", json=payload,
                     headers=_api_headers(), timeout=5)
    return r.ok


def _api_create_signer(payload: dict) -> tuple:
    r = requests.post(f"{API_BASE}/v1/signers", json=payload,
                      headers=_api_headers(), timeout=5)
    if r.ok:
        return True, ""
    try:
        return False, r.json().get("detail", r.text)
    except Exception:
        return False, r.text


def _api_delete_signer(sid: str) -> bool:
    r = requests.delete(f"{API_BASE}/v1/signers/{sid}",
                        headers=_api_headers(), timeout=5)
    return r.status_code == 204


def _render_aliases(alias_list: list, prefix: str, key_suffix: str) -> list:
    """Редактор таблицы алиасов (язык + значение)."""
    to_delete = []
    for i, alias in enumerate(alias_list):
        c1, c2, c3 = st.columns([2, 6, 1])
        with c1:
            cur = alias.get("language", "ru")
            alias["language"] = st.selectbox(
                "Язык", options=LANGUAGES,
                index=LANGUAGES.index(cur) if cur in LANGUAGES else 0,
                key=f"{prefix}_lang_{i}_{key_suffix}", label_visibility="collapsed",
            )
        with c2:
            alias["value"] = st.text_input(
                "Значение", value=alias.get("value", ""),
                key=f"{prefix}_val_{i}_{key_suffix}", label_visibility="collapsed",
            )
        with c3:
            if st.button("🗑", key=f"{prefix}_del_{i}_{key_suffix}"):
                to_delete.append(i)
    for idx in sorted(to_delete, reverse=True):
        alias_list.pop(idx)
    if to_delete:
        st.rerun()
    return alias_list


with tab_signer:
    import base64 as _b64

    # ── Список профилей ───────────────────────────────────────────────────────
    st.subheader("👥 Профили подписантов")

    profiles = _api_get_signers()
    profile_ids = [p["id"] for p in profiles]
    profile_labels = {p["id"]: f"{p.get('display') or p['id']}" +
                                (" ✍️" if p.get("has_signature") else " ⚠️ нет подписи")
                     for p in profiles}

    col_sel, col_new = st.columns([4, 2])
    with col_sel:
        if not profile_ids:
            st.warning("Нет профилей. Создай первый.")
            selected_id = None
        else:
            # Если после создания профиля нужно переключить selectbox —
            # используем pending-ключ, чтобы не нарушать ограничение Streamlit
            # на изменение widget-ключа после рендера.
            _pending = st.session_state.pop("_signer_pending_select", None)
            if _pending and _pending in profile_ids:
                st.session_state.pop("signer_selected_id", None)
                _sel_idx = profile_ids.index(_pending)
            else:
                _sel_idx = 0
            selected_id = st.selectbox(
                "Выбрать профиль",
                options=profile_ids,
                format_func=lambda x: profile_labels.get(x, x),
                index=_sel_idx,
                key="signer_selected_id",
                label_visibility="collapsed",
            )
    with col_new:
        if st.button("➕ Создать профиль", use_container_width=True, key="signer_create_btn"):
            st.session_state["signer_create_mode"] = True

    # ── Форма создания ────────────────────────────────────────────────────────
    if st.session_state.get("signer_create_mode"):
        with st.container(border=True):
            st.caption("Новый профиль подписанта")
            nc1, nc2 = st.columns(2)
            new_id = nc1.text_input(
                "ID профиля (slug)", placeholder="borisov",
                help="Только a-z, 0-9, _ или -, до 40 символов",
                key="signer_new_id",
            )
            new_display = nc2.text_input(
                "Отображаемое имя", placeholder="Vadim Borisov / Innowise",
                key="signer_new_display",
            )
            nb1, nb2 = st.columns(2)
            with nb1:
                if st.button("✅ Создать", type="primary", key="signer_create_ok"):
                    if not new_id.strip():
                        st.error("ID обязателен")
                    else:
                        ok, err = _api_create_signer({
                            "id": new_id.strip().lower(),
                            "display": new_display.strip(),
                            "match_markers": [],
                            "company_aliases": [],
                            "signer_aliases": [],
                        })
                        if ok:
                            st.session_state["signer_create_mode"] = False
                            st.session_state["_signer_pending_select"] = new_id.strip().lower()
                            st.success(f"Профиль «{new_id}» создан.")
                            st.rerun()
                        else:
                            st.error(f"Ошибка: {err}")
            with nb2:
                if st.button("Отмена", key="signer_create_cancel"):
                    st.session_state["signer_create_mode"] = False
                    st.rerun()

    st.divider()

    # ── Редактор выбранного профиля ───────────────────────────────────────────
    if selected_id:
        profile = _api_get_signer(selected_id)
        ks = selected_id  # key_suffix для виджетов

        # Инициализируем session_state для этого профиля
        ss_key = f"_sp_data_{selected_id}"
        if ss_key not in st.session_state or st.session_state.get(f"_sp_reload_{selected_id}"):
            st.session_state[ss_key] = {
                "display": profile.get("display", ""),
                "match_markers": list(profile.get("match_markers", [])),
                "company_aliases": [dict(a) for a in profile.get("company_aliases", [])],
                "signer_aliases": [dict(a) for a in profile.get("signer_aliases", [])],
            }
            st.session_state.pop(f"_sp_reload_{selected_id}", None)
        sp = st.session_state[ss_key]

        # Заголовок с иконкой удаления
        h1, h2 = st.columns([6, 2])
        h1.subheader(f"✏️ {profile_labels.get(selected_id, selected_id)}")
        if selected_id != "default":
            with h2:
                if st.button("🗑 Удалить профиль", key=f"sp_delete_{ks}"):
                    st.session_state[f"sp_del_confirm_{ks}"] = True
            if st.session_state.get(f"sp_del_confirm_{ks}"):
                st.warning(f"Удалить профиль **{selected_id}** и его подпись? Необратимо.")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("✅ Да, удалить", type="primary", key=f"sp_del_ok_{ks}"):
                        if _api_delete_signer(selected_id):
                            st.session_state.pop(ss_key, None)
                            st.session_state.pop(f"sp_del_confirm_{ks}", None)
                            st.success("Удалено.")
                            st.rerun()
                        else:
                            st.error("Ошибка удаления.")
                with dc2:
                    if st.button("Отмена", key=f"sp_del_cancel_{ks}"):
                        st.session_state.pop(f"sp_del_confirm_{ks}", None)
                        st.rerun()

        # Отображаемое имя
        sp["display"] = st.text_input(
            "Отображаемое имя",
            value=sp["display"],
            placeholder="Vadim Borisov / Innowise",
            key=f"sp_display_{ks}",
        )

        # Match markers
        st.caption(
            "**Маркеры авто-определения профиля** — короткое ядро названия нашей компании "
            "и имя подписанта. Система опознаёт профиль по вхождению этих строк в текст документа. "
            "⚠️ Не указывай рег.номера — они бывают не во всех документах."
        )
        markers_text = st.text_area(
            "Маркеры (по одному на строку)",
            value="\n".join(sp.get("match_markers", [])),
            height=100,
            key=f"sp_markers_{ks}",
            label_visibility="collapsed",
            placeholder="Innowise\nVadim Borisov\nВадим Борисов",
        )
        sp["match_markers"] = [m.strip() for m in markers_text.splitlines() if m.strip()]

        # Алиасы компании
        st.divider()
        st.subheader("🏢 Алиасы компании")
        st.caption("Как называется наша компания в договорах на разных языках")
        sp["company_aliases"] = _render_aliases(sp["company_aliases"], "company", ks)
        if st.button("+ Алиас компании", key=f"company_add_{ks}"):
            sp["company_aliases"].append({"language": "en", "value": ""})
            st.rerun()

        # Алиасы подписанта
        st.divider()
        st.subheader("👤 Алиасы подписанта")
        st.caption("Как пишется имя подписанта в договорах (транслитерации, инициалы)")
        if not sp.get("signer_aliases"):
            st.warning("⚠️ Не задан алиас подписанта.")
        sp["signer_aliases"] = _render_aliases(sp["signer_aliases"], "signer", ks)
        if st.button("+ Алиас подписанта", key=f"signer_add_{ks}"):
            sp["signer_aliases"].append({"language": "en", "value": ""})
            st.rerun()

        # Сохранить / Перечитать
        st.divider()
        sc1, sc2, sc3 = st.columns([2, 1, 3])
        with sc1:
            if st.button("💾 Сохранить профиль", type="primary", key=f"sp_save_{ks}"):
                if not any(a.get("value", "").strip() for a in sp.get("signer_aliases", [])):
                    st.error("Нужен хотя бы один алиас подписанта.")
                else:
                    payload = {
                        "display": sp["display"],
                        "match_markers": sp["match_markers"],
                        "company_aliases": sp["company_aliases"],
                        "signer_aliases": sp["signer_aliases"],
                    }
                    if _api_save_signer(selected_id, payload):
                        st.success("✅ Сохранено")
                        st.session_state[f"_sp_reload_{selected_id}"] = True
                        st.rerun()
                    else:
                        st.error("Ошибка сохранения.")
        with sc2:
            if st.button("🔄 Перечитать", key=f"sp_reload_{ks}"):
                st.session_state[f"_sp_reload_{selected_id}"] = True
                st.rerun()
        with sc3:
            with st.expander("Raw JSON профиля", expanded=False):
                import json as _json
                st.code(_json.dumps(sp, ensure_ascii=False, indent=2), language="json")

        # ── Подпись ───────────────────────────────────────────────────────────
        st.divider()
        st.subheader("✍️ Подпись")

        # Показать текущую подпись — всегда загружаем актуальную (без кэша session_state)
        current_sig_key = f"signature_png_{selected_id}"
        try:
            client_inner = get_api_client()
            png = client_inner.get_signature_png(selected_id)
            if png:
                st.session_state[current_sig_key] = png
            else:
                st.session_state.pop(current_sig_key, None)
        except Exception:
            pass

        current_sig = st.session_state.get(current_sig_key)
        if current_sig:
            st.markdown(_sig_html(current_sig, width=280), unsafe_allow_html=True)
        else:
            st.warning("Подпись не загружена.")

        # Загрузка новой подписи
        st.caption("Загрузить / заменить подпись")
        uploaded_sig = st.file_uploader(
            "PNG / JPG / GIF", type=["png", "jpg", "jpeg", "gif"],
            key=f"sig_uploader_{ks}",
        )

        if uploaded_sig is not None:
            file_key = f"{selected_id}_{uploaded_sig.name}_{uploaded_sig.size}"
            if st.session_state.get(f"_sig_file_key_{ks}") != file_key:
                st.session_state[f"_sig_file_key_{ks}"] = file_key
                st.session_state.pop(f"sig_proc_result_{ks}", None)
                uploaded_sig.seek(0)
                raw_bytes = uploaded_sig.read()
                st.session_state[f"sig_raw_{ks}"] = (raw_bytes, uploaded_sig.name, uploaded_sig.type)
                with st.spinner("Обрабатываю..."):
                    try:
                        client_inner = get_api_client()
                        resp = requests.post(
                            f"{client_inner.base_url}/v1/signers/{selected_id}/signature/process",
                            files={"file": (uploaded_sig.name, raw_bytes, uploaded_sig.type)},
                            headers=client_inner._headers, timeout=30,
                        )
                        if resp.status_code == 200:
                            st.session_state[f"sig_proc_result_{ks}"] = resp.json()
                    except Exception:
                        pass
                st.rerun()

            raw_tuple = st.session_state.get(f"sig_raw_{ks}", (b"", "", "image/png"))
            raw_bytes, raw_name, raw_type = raw_tuple
            proc = st.session_state.get(f"sig_proc_result_{ks}")

            def _save_signature(data: bytes, mime: str, fname: str) -> None:
                client_inner = get_api_client()
                r = requests.put(
                    f"{client_inner.base_url}/v1/signers/{selected_id}/signature",
                    files={"file": (fname, data, mime)},
                    headers=client_inner._headers, timeout=10,
                )
                if r.status_code == 204:
                    st.session_state[current_sig_key] = data
                    st.session_state.pop(f"sig_proc_result_{ks}", None)
                    st.session_state.pop(f"_sig_file_key_{ks}", None)
                    st.success("✅ Подпись сохранена")
                    st.rerun()
                else:
                    st.error(r.text)

            if proc:
                png_bytes = _b64.b64decode(proc["processed_png_b64"])
                col_orig, col_proc = st.columns(2)
                col_orig.caption("Исходник")
                col_orig.markdown(_sig_html(raw_bytes, width=240), unsafe_allow_html=True)
                col_proc.caption("Обработанная")
                col_proc.markdown(_sig_html(png_bytes, width=240), unsafe_allow_html=True)
                m1, m2, m3 = st.columns(3)
                m1.metric("Уверенность", f"{proc['confidence']:.0%}")
                m2.metric("Размер", f"{proc['output_size'][0]}×{proc['output_size'][1]}")
                m3.metric("Coverage", f"{proc['ink_coverage']:.1%}")
                for w in proc.get("warnings", []):
                    st.warning(w)
                sb1, sb2 = st.columns(2)
                with sb1:
                    if st.button("💾 Сохранить обработанную", type="primary",
                                 key=f"sig_save_proc_{ks}"):
                        _save_signature(png_bytes, "image/png", "signature.png")
                with sb2:
                    if st.button("💾 Сохранить оригинал", key=f"sig_save_orig_{ks}"):
                        _save_signature(raw_bytes, raw_type, raw_name)
            else:
                if st.button("💾 Сохранить подпись", type="primary", key=f"sig_save_direct_{ks}"):
                    _save_signature(raw_bytes, raw_type, raw_name)

    # ── Режим простановки ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("🖊 Режим простановки")

    try:
        r_mode = requests.get(f"{API_BASE}/v1/settings/sign-mode",
                              headers=_api_headers(), timeout=5)
        current_mode = r_mode.json() if r_mode.ok else {}
    except Exception:
        current_mode = {}

    use_sig = st.checkbox(
        "✍️ Проставить подпись PNG",
        value=current_mode.get("use_signature", True),
        key="mode_use_sig",
    )
    use_mrk = st.checkbox(
        "🏷 Поставить маркер места подписи",
        value=current_mode.get("use_marker", False),
        key="mode_use_mrk",
    )
    sign_above_line = st.checkbox(
        "✍️ Подпись над линией (для двуязычных договоров)",
        value=current_mode.get("sign_above_line", False),
        key="mode_sign_above_line",
        help="Подпись ставится НАД подчёркиванием. Для одноязычных (Лебедев) — выключить.",
    )
    default_page = st.radio(
        "📄 Первая страница при открытии в Разборе",
        options=["last", "first"],
        format_func=lambda x: "Последняя страница" if x == "last" else "Первая страница",
        index=0 if current_mode.get("default_page", "last") == "last" else 1,
        horizontal=True,
        key="mode_default_page",
    )
    marker_color = "pink"
    if use_mrk:
        marker_color = st.radio(
            "Цвет маркера",
            options=["pink", "gray"],
            format_func=lambda x: "Розовый (цветная печать)" if x == "pink" else "Серый (ч/б печать)",
            index=0 if current_mode.get("marker_color", "pink") == "pink" else 1,
            horizontal=True, key="mode_marker_color",
        )
    if st.button("💾 Сохранить режим", key="mode_save"):
        try:
            r_save = requests.put(
                f"{API_BASE}/v1/settings/sign-mode",
                json={"use_signature": use_sig, "use_marker": use_mrk,
                      "marker_color": marker_color, "sign_above_line": sign_above_line,
                      "default_page": default_page},
                headers=_api_headers(), timeout=5,
            )
            st.success("Сохранено.") if r_save.ok else st.error(r_save.text)
        except Exception as e:
            st.error(f"Ошибка: {e}")
    if not use_sig and not use_mrk:
        st.warning("Включи хотя бы один режим.")


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 3: Маркеры
# ══════════════════════════════════════════════════════════════════════════════
with tab_markers:
    st.caption("Универсальные маркеры. API: `GET/PUT /v1/settings/markers`.")
    client = get_api_client()
    if "markers_api_raw" not in st.session_state:
        try:
            st.session_state["markers_api_raw"] = json.dumps(client.get_markers_config(), ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"API недоступен: {e}")
            st.session_state["markers_api_raw"] = "{}"
    col_m_save, col_m_reset, col_m_reload = st.columns([1, 1, 2])
    with col_m_save:
        if st.button("💾 Сохранить маркеры", type="primary", key="markers_save"):
            raw_text = st.session_state.get("markers_editor", "")
            try:
                client.update_markers_config(json.loads(raw_text))
                st.success("Сохранено.")
                st.session_state["markers_api_raw"] = raw_text
            except json.JSONDecodeError as e:
                st.error(f"Невалидный JSON: {e}")
            except Exception as e:
                st.error(f"Ошибка API: {e}")
    with col_m_reset:
        if st.button("↩ Сбросить", key="markers_reset"):
            try:
                from core.markers import DEFAULTS as MARKERS_DEFAULTS
                client.update_markers_config(MARKERS_DEFAULTS)
                st.session_state["markers_api_raw"] = json.dumps(MARKERS_DEFAULTS, ensure_ascii=False, indent=2)
                st.success("Сброшено.")
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка: {e}")
    with col_m_reload:
        if st.button("🔄 Перечитать", key="markers_reload"):
            st.session_state.pop("markers_api_raw", None)
            st.rerun()
    st.divider()
    st.text_area("markers config (JSON)", value=st.session_state.get("markers_api_raw", "{}"),
                 height=500, key="markers_editor", label_visibility="collapsed")


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 4: LLM
# ══════════════════════════════════════════════════════════════════════════════
with tab_llm:
    PROVIDER_LABELS: dict[str, str] = {
        "anthropic": "Anthropic (Claude)",
        "openai":    "OpenAI (GPT-4o)",
        "deepseek":  "DeepSeek",
        "gemini":    "Google Gemini",
    }

    @st.cache_data(ttl=5)
    def _fetch_llm_config() -> dict:
        r = requests.get(f"{API_BASE}/v1/config/llm", headers=_api_headers(), timeout=5)
        r.raise_for_status()
        return r.json()

    def _save_llm_config(payload: dict) -> dict:
        r = requests.post(f"{API_BASE}/v1/config/llm", json=payload, headers=_api_headers(), timeout=5)
        r.raise_for_status()
        return r.json()

    def _test_llm_provider(provider: str, api_key: str = "") -> dict:
        body: dict = {"provider": provider}
        if api_key:
            body["api_key"] = api_key
        r = requests.post(f"{API_BASE}/v1/config/llm/test", json=body, headers=_api_headers(), timeout=30)
        return r.json() if r.ok else {"success": False, "error": r.text}

    try:
        llm_cfg = _fetch_llm_config()
    except Exception as e:
        st.error(f"API недоступен: {e}")
        st.stop()

    providers_data = llm_cfg.get("providers", {})
    configured = llm_cfg.get("configured", [])
    active_current = llm_cfg.get("active_provider", "")

    st.subheader("Провайдеры")
    new_keys: dict[str, str] = {}

    for provider, label in PROVIDER_LABELS.items():
        pdata = providers_data.get(provider, {})
        is_configured = pdata.get("configured", False)
        icon = "✅" if is_configured else "⚠️"
        status = "настроен" if is_configured else "не настроен"

        with st.expander(f"{icon} {label} — {status}", expanded=not is_configured):
            col_key, col_btn = st.columns([4, 1])
            with col_key:
                new_keys[provider] = st.text_input(
                    "API Key", value="",
                    placeholder=pdata.get("api_key", "") if is_configured else f"Введите ключ для {label}",
                    type="password", key=f"llm_key_{provider}", label_visibility="collapsed",
                )
            with col_btn:
                has_new_key = bool(new_keys[provider].strip())
                if is_configured or has_new_key:
                    st.write("")
                    if st.button("🔍 Тест", key=f"llm_test_{provider}"):
                        with st.spinner("Проверяю..."):
                            result = _test_llm_provider(
                                provider,
                                api_key=new_keys[provider].strip() if has_new_key else "",
                            )
                        if result.get("success"):
                            st.success("OK")
                        else:
                            st.error(result.get("error", "Ошибка"))

    st.divider()
    st.subheader("Активный провайдер")

    newly_entered = [p for p in PROVIDER_LABELS if new_keys.get(p, "").strip()]
    available = list(dict.fromkeys(configured + newly_entered))
    has_any_key = bool(available)

    if not has_any_key:
        st.warning("Нет настроенных провайдеров. Введи ключ и нажми «Сохранить».")
        active_choice = None
    else:
        idx = available.index(active_current) if active_current in available else 0
        active_choice = st.radio(
            "Выбрать:", options=available,
            format_func=lambda p: PROVIDER_LABELS.get(p, p),
            index=idx, horizontal=True, label_visibility="collapsed",
        )

    st.divider()
    if st.button("💾 Сохранить", type="primary", disabled=not has_any_key, key="llm_save"):
        try:
            result = _save_llm_config({
                "active_provider": active_choice or "",
                "providers": {p: {"api_key": new_keys.get(p, "")} for p in PROVIDER_LABELS},
            })
            st.success(f"Сохранено. Активный: **{PROVIDER_LABELS.get(result['active_provider'], result['active_provider'])}**")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка: {e}")

    st.divider()
    st.caption(f"SignFinder v{_sf_version()}")


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 6: Mail
# ══════════════════════════════════════════════════════════════════════════════
with tab_mail:
    if st.session_state.pop("_mail_toast", False):
        st.toast("✅ Сохранено")

    cfg_mail = _load_mail_cfg()

    for _k, _dv in _MAIL_DEF.items():
        _wk = f"mail_{_k}"
        if _wk not in st.session_state:
            if _k in _SECRET_KEYS:
                st.session_state[_wk] = ""
            elif isinstance(_dv, int):
                st.session_state[_wk] = int(cfg_mail.get(_k, _dv))
            elif isinstance(_dv, bool):
                st.session_state[_wk] = bool(cfg_mail.get(_k, _dv))
            else:
                st.session_state[_wk] = cfg_mail.get(_k, _dv)

    # ── Способ аутентификации ─────────────────────────────────────────────────
    st.subheader("🔐 Аутентификация")
    auth_method = st.radio(
        "Способ аутентификации",
        options=["basic", "xoauth2"],
        format_func=lambda x: "Пароль (basic)" if x == "basic" else "OAuth2 (XOAUTH2)",
        horizontal=True, key="mail_auth_method", on_change=_autosave_mail,
    )

    if auth_method == "basic":
        # IMAP
        st.subheader("📬 IMAP")
        _mc1, _mc2 = st.columns(2)
        _mc1.text_input("Host", key="mail_imap_host", on_change=_autosave_mail)
        _mc2.number_input("Port", min_value=1, max_value=65535, step=1,
                          key="mail_imap_port", on_change=_autosave_mail)
        _mc1.text_input("User", key="mail_imap_user", on_change=_autosave_mail)
        _mc2.text_input(
            "Password",
            placeholder="••••••••" if cfg_mail.get("imap_password") else "Введите пароль",
            type="password", key="mail_imap_password", on_change=_autosave_mail,
        )
        _mc1.checkbox("SSL", key="mail_imap_ssl", on_change=_autosave_mail)

        # SMTP
        st.subheader("📤 SMTP")
        _ms1, _ms2 = st.columns(2)
        _ms1.text_input("Host", key="mail_smtp_host", on_change=_autosave_mail)
        _ms2.number_input("Port", min_value=1, max_value=65535, step=1,
                          key="mail_smtp_port", on_change=_autosave_mail)
        _ms1.text_input("User", key="mail_smtp_user", on_change=_autosave_mail)
        _ms2.text_input(
            "Password",
            placeholder="••••••••" if cfg_mail.get("smtp_password") else "Введите пароль",
            type="password", key="mail_smtp_password", on_change=_autosave_mail,
        )
    else:
        # OAuth2 — прогрессивное раскрытие
        provider = st.selectbox(
            "Провайдер OAuth2",
            options=list(_OAUTH_PRESETS.keys()),
            format_func=lambda p: _OAUTH_PRESETS[p]["label"],
            key="mail_oauth2_provider", on_change=_on_provider_change,
        )
        preset = _OAUTH_PRESETS[provider]
        st.caption(
            f"IMAP: **{preset['imap_host']}:{preset['imap_port']}** · "
            f"SMTP: **{preset['smtp_host']}:{preset['smtp_port']}**"
        )
        st.caption(f"Scope для refresh_token: `{preset['scope_hint']}`")

        st.text_input("User (email)", key="mail_imap_user", on_change=_autosave_mail)
        st.text_input("Client ID", key="mail_oauth2_client_id", on_change=_autosave_mail)
        st.text_input("Client Secret", type="password",
                      placeholder="••••••••" if cfg_mail.get("oauth2_client_secret") else "",
                      key="mail_oauth2_client_secret", on_change=_autosave_mail)
        st.text_input("Refresh Token", type="password",
                      placeholder="••••••••" if cfg_mail.get("oauth2_refresh_token") else "",
                      key="mail_oauth2_refresh_token", on_change=_autosave_mail)
        st.caption("Refresh token получается одноразово — см. `OAUTH2_SETUP.md`")

        with st.expander("⚙️ Расширенные (override хостов)", expanded=False):
            _oa1, _oa2 = st.columns(2)
            _oa1.text_input("IMAP Host", key="mail_imap_host", on_change=_autosave_mail)
            _oa2.number_input("IMAP Port", min_value=1, max_value=65535, step=1,
                              key="mail_imap_port", on_change=_autosave_mail)
            _oa1.text_input("SMTP Host", key="mail_smtp_host", on_change=_autosave_mail)
            _oa2.number_input("SMTP Port", min_value=1, max_value=65535, step=1,
                              key="mail_smtp_port", on_change=_autosave_mail)
            _oa1.checkbox("SSL", key="mail_imap_ssl", on_change=_autosave_mail)
            st.text_input("Token Endpoint (override)",
                          key="mail_oauth2_token_endpoint", on_change=_autosave_mail)

    # Агент
    st.subheader("⚙️ Агент")
    _ma1, _ma2 = st.columns(2)
    _ma1.number_input("Интервал опроса (сек)", min_value=60, step=30,
                      key="mail_poll_interval_sec", on_change=_autosave_mail)
    _ma2.checkbox("Reply to sender", key="mail_reply_to_sender", on_change=_autosave_mail)

    # Папки IMAP
    st.subheader("📁 Папки IMAP")
    _folder_labels = [
        ("folder_in",      "Входящие (In)"),
        ("folder_green",   "Зелёные (Green)"),
        ("folder_yellow",  "Жёлтые (Yellow)"),
        ("folder_red",     "Красные (Red)"),
        ("folder_archive", "Архив (Archive)"),
    ]
    _mf1, _mf2 = st.columns(2)
    for _fi, (_fk, _fl) in enumerate(_folder_labels):
        _fcol = _mf1 if _fi % 2 == 0 else _mf2
        _fcol.text_input(_fl, key=f"mail_{_fk}", on_change=_autosave_mail)

    # Тест IMAP
    st.divider()
    if st.button("🔍 Тест IMAP", key="mail_imap_test"):
        _imap_host = cfg_mail.get("imap_host", "")
        if not _imap_host:
            st.warning("Укажи IMAP Host и сохрани настройки.")
        else:
            with st.spinner("Подключаюсь..."):
                try:
                    import imaplib as _imaplib_test
                    _cfg_now = _load_mail_cfg()
                    _ssl = _cfg_now.get("imap_ssl", True)
                    _port = int(_cfg_now.get("imap_port", 993))
                    _M = _imaplib_test.IMAP4_SSL(_imap_host, _port) if _ssl else _imaplib_test.IMAP4(_imap_host, _port)
                    if _cfg_now.get("auth_method") == "xoauth2":
                        from signfinder.intake.oauth2 import OAuth2TokenProvider, build_xoauth2_string
                        _prov = OAuth2TokenProvider(
                            provider=_cfg_now.get("oauth2_provider", "google"),
                            client_id=_cfg_now.get("oauth2_client_id", ""),
                            client_secret=_cfg_now.get("oauth2_client_secret", ""),
                            refresh_token=_cfg_now.get("oauth2_refresh_token", ""),
                            token_endpoint=_cfg_now.get("oauth2_token_endpoint", ""),
                        )
                        _tok = _prov.get_access_token()
                        _auth_b = build_xoauth2_string(_cfg_now.get("imap_user", ""), _tok)
                        _M.authenticate("XOAUTH2", lambda _: _auth_b)
                    else:
                        _M.login(_cfg_now.get("imap_user", ""), _cfg_now.get("imap_password", ""))
                    _M.logout()
                    st.success("✅ IMAP подключение OK")
                except Exception as _e:
                    st.error(f"❌ {_e}")


# ══════════════════════════════════════════════════════════════════════════════
# ТАБ 5: Тестирование (v1.15)
# ══════════════════════════════════════════════════════════════════════════════
with tab_test:
    import os as _os
    import requests as _req
    from core.test_runner import run_quick_tests, run_integration_tests, run_full_eval

    st.subheader("🧪 Тестирование")

    # ── Быстрые тесты (unit) ─────────────────────────────────────────────────
    st.markdown("#### Быстрые тесты (unit + integration API)")
    st.caption("Pytest на детерминированном ядре. ~10–30 сек, без LLM.")

    col_run_q, col_run_i = st.columns(2)

    with col_run_q:
        if st.button("▶ Запустить unit-тесты", key="test_run_unit", use_container_width=True):
            with st.spinner("pytest /app/sf_tests/ …"):
                st.session_state["unit_result"] = run_quick_tests(timeout=120)

    with col_run_i:
        if st.button("▶ API integration", key="test_run_int", use_container_width=True):
            with st.spinner("pytest test_api_integration …"):
                st.session_state["int_result"] = run_integration_tests(timeout=60)

    # Отображаем результат unit-тестов
    unit_res = st.session_state.get("unit_result")
    if unit_res:
        status = unit_res["status"]
        icon = "✅" if status == "passed" else ("❌" if status == "failed" else "⚠️")
        err_msg = unit_res.get("error_message")
        if err_msg:
            st.error(f"⚠️ {err_msg}")
        else:
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            col_s1.metric(f"{icon} Статус", status)
            col_s2.metric("✅ Passed", unit_res["passed"])
            col_s3.metric("❌ Failed", unit_res["failed"])
            col_s4.metric("⏱ Время", f"{unit_res['duration_sec']:.1f} сек")

            details = unit_res.get("details", [])
            if details:
                import pandas as _pd
                df_det = _pd.DataFrame(details)
                st.dataframe(df_det, use_container_width=True, hide_index=True)

            with st.expander("📄 Полный вывод pytest", expanded=(status != "passed")):
                st.code(unit_res.get("output", ""), language="text")

    # Отображаем результат integration-тестов
    int_res = st.session_state.get("int_result")
    if int_res:
        icon_i = "✅" if int_res["status"] == "passed" else "❌"
        col_i1, col_i2, col_i3 = st.columns(3)
        col_i1.metric(f"{icon_i} API integration", int_res["status"])
        col_i2.metric("Passed", int_res["passed"])
        col_i3.metric("Failed", int_res["failed"])
        with st.expander("📄 Вывод", expanded=(int_res["status"] != "passed")):
            st.code(int_res.get("output", ""), language="text")

    st.divider()

    # ── Полный прогон на корпусе (LLM eval) ─────────────────────────────────
    st.markdown("#### Полный прогон на корпусе (LLM eval)")

    # Читаем корпус
    corpus_data = None
    try:
        r_corpus = _req.get(f"{API_BASE}/v1/corpus", headers={"Authorization": f"Bearer {_os.environ.get('SIGNFINDER_API_KEY','')}"}  , timeout=5)
        if r_corpus.ok:
            corpus_data = r_corpus.json()
    except Exception:
        pass

    n_docs = len((corpus_data or {}).get("documents", []))
    if n_docs == 0:
        st.warning(
            "Корпус пуст. Прогони анализ на странице **Пакетная обработка**, "
            "затем нажми «💾 Сохранить как корпус» ниже."
        )
    else:
        st.info(f"Корпус: **{n_docs}** документов. Файл: `data/api/corpus/corpus.json`")

    EVAL_PROVIDERS = {"anthropic": "Anthropic (Claude)", "deepseek": "DeepSeek", "openai": "OpenAI", "gemini": "Gemini"}
    selected_providers = st.multiselect(
        "Провайдеры для eval:",
        options=list(EVAL_PROVIDERS.keys()),
        default=["anthropic"],
        format_func=lambda p: EVAL_PROVIDERS.get(p, p),
        key="eval_providers",
    )

    run_eval_disabled = n_docs == 0 or not selected_providers
    if st.button("▶ Запустить полный прогон", disabled=run_eval_disabled, key="test_run_eval", use_container_width=True):
        with st.spinner(f"Прогон {n_docs} документов × {len(selected_providers)} провайдеров…"):
            eval_result = run_full_eval(
                api_base_url=API_BASE,
                api_key=_os.environ.get("SIGNFINDER_API_KEY", ""),
                corpus=corpus_data or {},
                providers=selected_providers,
            )
            st.session_state["eval_result"] = eval_result

    eval_res = st.session_state.get("eval_result")
    if eval_res:
        import pandas as _pd
        kpi_rows = []
        for prov, kpi in eval_res.items():
            kpi_rows.append({
                "Провайдер": EVAL_PROVIDERS.get(prov, prov),
                "TL Accuracy": f"{kpi.get('traffic_light_accuracy', 0):.0%}",
                "Template Acc.": f"{kpi.get('template_accuracy', 0):.0%}",
                "Latency p50": f"{kpi.get('latency_p50_ms', 0):.0f} мс",
                "Latency p95": f"{kpi.get('latency_p95_ms', 0):.0f} мс",
                "Docs": kpi.get("total_docs", 0),
                "Errors": kpi.get("errors", 0),
            })
        if kpi_rows:
            st.dataframe(_pd.DataFrame(kpi_rows), use_container_width=True, hide_index=True)

        first_prov = next(iter(eval_res))
        per_doc = eval_res[first_prov].get("per_doc", [])
        if per_doc:
            with st.expander("📋 Детали по документам", expanded=False):
                doc_rows = []
                for d in per_doc:
                    doc_rows.append({
                        "Файл": d.get("filename", "?"),
                        "Ожидалось": d.get("expected_tl", "-"),
                        "Факт": d.get("actual_tl") or "-",
                        "✓": "✅" if d.get("match") else "❌",
                        "Примечание": d.get("note", ""),
                    })
                st.dataframe(_pd.DataFrame(doc_rows), use_container_width=True, hide_index=True)

    # ── Сохранить как корпус ──────────────────────────────────────────────────
    st.divider()
    st.subheader("💾 Сохранить как корпус")
    st.caption(
        "Сохраняет результаты последнего пакетного анализа как `data/api/corpus/corpus.json`. "
        "Перед запуском eval — проверь expected-поля вручную."
    )

    _batch_items = (st.session_state.get("batch_result") or {}).get("items", [])
    if not _batch_items:
        st.info("Нет результатов пакетного анализа. Запусти анализ на странице **Пакетная обработка**.")

    if st.button("💾 Сохранить как корпус", key="save_corpus_test", disabled=not _batch_items):
        from datetime import datetime as _dt, timezone as _tz
        import os as _os
        import requests as _rq

        _corpus_docs = []
        for _it in _batch_items:
            _analysis = _it.get("analysis") or {}
            _tl = _analysis.get("traffic_light", "yellow") if _analysis else "yellow"
            _mt = _analysis.get("matched_template") or {}
            _corpus_docs.append({
                "filename": _it.get("filename", "?"),
                "expected_template_name": _mt.get("best_match_template_id", ""),
                "expected_traffic_light": _tl,
                "expected_signature_count": len(_analysis.get("anchors", [])),
                "expected_our_side": _analysis.get("our_side") or {},
                "variant_type": "base",
                "notes": f"Из пакета {_dt.now(_tz.utc).strftime('%Y-%m-%d')}",
            })

        _corpus_payload = {
            "corpus_version": "1.0",
            "created_at": _dt.now(_tz.utc).isoformat(),
            "description": f"Batch {_dt.now(_tz.utc).strftime('%Y-%m-%d')}, {len(_corpus_docs)} docs",
            "documents": _corpus_docs,
        }

        try:
            _api_base_c = _os.environ.get("API_URL", "http://api:8000")
            _api_key_c = _os.environ.get("SIGNFINDER_API_KEY", "")
            _rc = _rq.put(
                f"{_api_base_c}/v1/corpus",
                json=_corpus_payload,
                headers={"Authorization": f"Bearer {_api_key_c}"},
                timeout=10,
            )
            if _rc.ok:
                _raw_files = st.session_state.get("batch_files_raw", {})
                _uploaded_cnt = 0
                _missing = []
                for _it in _batch_items:
                    _fn = _it.get("filename", "?")
                    _fb = _raw_files.get(_fn)
                    if not _fb:
                        _missing.append(_fn)
                        continue
                    try:
                        _ru = _rq.put(
                            f"{_api_base_c}/v1/corpus/files/{_fn}",
                            files={"file": (_fn, _fb, "application/pdf")},
                            headers={"Authorization": f"Bearer {_api_key_c}"},
                            timeout=30,
                        )
                        if _ru.ok:
                            _uploaded_cnt += 1
                    except Exception:
                        pass

                _msg = (f"Сохранено {len(_corpus_docs)} документов, "
                        f"файлов залито: {_uploaded_cnt}/{len(_batch_items)}. "
                        "Проверь expected-поля в `data/api/corpus/corpus.json`.")
                if _missing:
                    _msg += (f" ⚠️ Нет байтов для {len(_missing)} файлов "
                             "(перезапусти анализ на Пакете, затем пересохрани) — eval их пропустит.")
                st.success(_msg)
            else:
                st.error(f"Ошибка API: {_rc.status_code} {_rc.text[:200]}")
        except Exception as _e:
            st.error(f"Ошибка: {_e}")

    st.caption(f"SignFinder v{_sf_version()}")
