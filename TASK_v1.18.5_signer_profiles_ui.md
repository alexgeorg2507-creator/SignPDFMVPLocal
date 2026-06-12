# SignFinder v1.18.5 — UI профилей подписантов в Streamlit

Прочитай `C:\work\CLAUDE.md` перед началом.
Изменения только в одном файле:
`C:\work\SignPDFMVPLocal\streamlit\views\4_Nastroyki.py`

Деплой: только streamlit — `docker compose build streamlit && docker compose up -d --force-recreate streamlit`

---

## Контекст

v1.18.3 (core) и v1.18.4 (api) добавили полноценные профили подписантов.
Сейчас таб «Подписант» в настройках:
- работает только с "default"
- использует старое `core.signer_profile` напрямую (не через API)
- не знает про match_markers, несколько профилей

Задача: переписать таб «Подписант» на новые API-эндпоинты + multi-profile UI.
Остальные 6 табов НЕ трогать.

---

## Изменение 1 — LANGUAGES (строка ~12)

Добавить macedonian:
```python
LANGUAGES = ["ru", "en", "pl", "mk"]
```

---

## Изменение 2 — Полная замена блока `with tab_signer:`

Найти блок от строки `with tab_signer:` до начала `with tab_markers:` и заменить
целиком на код ниже.

Логика UI:
1. Список профилей (selectbox) + кнопка «Создать»
2. Форма создания (появляется при нажатии «Создать»)
3. Редактор выбранного профиля: display, match_markers, aliases, подпись
4. Режим простановки — внизу, без изменений

```python
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


def _api_create_signer(payload: dict) -> tuple[bool, str]:
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
            selected_id = st.selectbox(
                "Выбрать профиль",
                options=profile_ids,
                format_func=lambda x: profile_labels.get(x, x),
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
                            st.session_state["signer_selected_id"] = new_id.strip().lower()
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

        # Показать текущую подпись
        current_sig_key = f"signature_png_{selected_id}"
        if not st.session_state.get(current_sig_key):
            try:
                client_inner = get_api_client()
                png = client_inner.get_signature_png(selected_id)
                if png:
                    st.session_state[current_sig_key] = png
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
                      "marker_color": marker_color},
                headers=_api_headers(), timeout=5,
            )
            st.success("Сохранено.") if r_save.ok else st.error(r_save.text)
        except Exception as e:
            st.error(f"Ошибка: {e}")
    if not use_sig and not use_mrk:
        st.warning("Включи хотя бы один режим.")
```

---

## Деплой

```powershell
cd C:\work\SignPDFMVPLocal
docker compose build streamlit
docker compose up -d --force-recreate streamlit
```

Core и api не менялись — только streamlit.

---

## Тест

1. Настройки → таб «Подписант»
2. Видны профили из API: список с selectbox (минимум «default»)
3. «➕ Создать профиль» → вводим id=borisov, display=«Vadim Borisov / Innowise» → Создать
4. Выбрать «borisov» в selectbox → открывается редактор
5. Добавить маркеры: Innowise, Vadim Borisov, Вадим Борисов
6. Добавить алиасы компании (en/pl/mk) + алиасы подписанта
7. «💾 Сохранить профиль» → OK
8. Загрузить PNG подписи Borisov → auto_process → «Сохранить обработанную»
9. В selectbox у borisov появляется ✍️ (не ⚠️)
10. «default» — кнопки удаления нет (защита)
11. LANGUAGES = ["ru", "en", "pl", "mk"] — македонский в дропдаунах алиасов

---

## Что НЕ делается здесь

- Агент (v1.18.6)
- Колонки (отдельное направление)
- LANGUAGES добавлен в список виджетов, в анализ языка (parser.py) — позже

## Стиль

Коротко, технично, по-русски. Файлы на диск, не в чат.
