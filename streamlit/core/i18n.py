"""Интернационализация SignFinder.

Использование:
    from core.i18n import t
    st.button(t("btn_sign"))
    st.caption(t("caption_pages", n=5))   # шаблонные строки через **kwargs
"""
import streamlit as st


TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── ОБЩИЕ ─────────────────────────────────────────────────────────────
    "app_title":           {"ru": "🔐 SignFinder", "en": "🔐 SignFinder"},
    "access_code":         {"ru": "Код доступа", "en": "Access code"},
    "btn_login":           {"ru": "Войти", "en": "Log in"},
    "err_wrong_code":      {"ru": "Неверный код", "en": "Wrong code"},
    "lang_selector":       {"ru": "Язык / Language", "en": "Язык / Language"},
    "warn_login_required": {"ru": "Войдите через главную страницу.",
                            "en": "Please log in from the main page."},

    # ── НАВИГАЦИЯ ─────────────────────────────────────────────────────────
    "nav_batch":    {"ru": "📦 Пакетная обработка", "en": "📦 Batch processing"},
    "nav_settings": {"ru": "⚙️ Настройки",          "en": "⚙️ Settings"},
    "nav_review":   {"ru": "✍️ Разбор и подписание", "en": "✍️ Review & Sign"},
    "nav_agent":    {"ru": "📧 Агент Mail",           "en": "📧 Mail Agent"},

    # ── СВЕТОФОР ──────────────────────────────────────────────────────────
    "tl_green":    {"ru": "Шаблон применён",       "en": "Template applied"},
    "tl_yellow":   {"ru": "Проверка оператором",   "en": "Operator review"},
    "tl_no_match": {"ru": "Сбой",                  "en": "Failed"},

    # ── ПАКЕТНАЯ ОБРАБОТКА (3_Paket.py) ──────────────────────────────────
    "batch_title":          {"ru": "📦 Пакетная обработка",
                             "en": "📦 Batch processing"},
    "batch_caption":        {"ru": "Загрузи до 100 договоров — система проанализирует пакетом. "
                                   "Жёлтые отправь в «Разбор» для проверки оператором.",
                             "en": "Upload up to 100 contracts — the system will analyse them as a batch. "
                                   "Send yellow ones to «Review» for operator check."},
    "batch_uploader":       {"ru": "Загрузить договоры (PDF/DOCX, до 100)",
                             "en": "Upload contracts (PDF/DOCX, up to 100)"},
    "batch_btn_run":        {"ru": "▶ Анализировать ({n})", "en": "▶ Analyse ({n})"},
    "batch_btn_reset":      {"ru": "🗑 Сбросить",  "en": "🗑 Reset"},
    "batch_err_max":        {"ru": "Максимум {max} файлов. Загружено: {n}.",
                             "en": "Maximum {max} files. Uploaded: {n}."},
    "batch_preparing":      {"ru": "Подготовка файлов...",    "en": "Preparing files..."},
    "batch_converting":     {"ru": " DOCX→PDF конвертация через LibreOffice...",
                             "en": " DOCX→PDF conversion via LibreOffice..."},
    "batch_err_convert":    {"ru": "Не удалось конвертировать {name}: {err}",
                             "en": "Failed to convert {name}: {err}"},
    "batch_err_no_files":   {"ru": "Нет файлов для анализа после конвертации.",
                             "en": "No files to analyse after conversion."},
    "batch_analyzing":      {"ru": "Анализирую {n} документов... LLM на каждый — это небыстро.",
                             "en": "Analysing {n} documents… LLM per document — this takes a while."},
    "batch_err_batch":      {"ru": "Ошибка batch-анализа: {err}",
                             "en": "Batch analysis error: {err}"},
    "metric_total":         {"ru": "Всего",          "en": "Total"},
    "metric_processed":     {"ru": "🟢🟡 Обработано", "en": "🟢🟡 Processed"},
    "metric_failed":        {"ru": "🔴 Сбой",         "en": "🔴 Failed"},
    "metric_review":        {"ru": "🟡 На проверку",  "en": "🟡 For review"},
    "col_file":             {"ru": "Файл",    "en": "File"},
    "col_status":           {"ru": "Статус",  "en": "Status"},
    "col_template":         {"ru": "Шаблон",  "en": "Template"},
    "col_score":            {"ru": "Score",   "en": "Score"},
    "col_zones":            {"ru": "Зон",     "en": "Zones"},
    "col_time":             {"ru": "Время",   "en": "Time"},
    "col_error":            {"ru": "Ошибка",  "en": "Error"},
    "batch_actions":        {"ru": "Действия по документу", "en": "Document actions"},
    "batch_select":         {"ru": "Выбрать документ",      "en": "Select document"},
    "batch_details":        {"ru": "🔬 Детали анализа",     "en": "🔬 Analysis details"},
    "lbl_traffic_light":    {"ru": "Светофор:",   "en": "Traffic light:"},
    "lbl_api_error":        {"ru": "Ошибка:",     "en": "Error:"},
    "metric_candidates":    {"ru": "Кандидатов",  "en": "Candidates"},
    "metric_anchors":       {"ru": "Якорей",      "en": "Anchors"},
    "metric_fp_pages":      {"ru": "Страниц (fp)","en": "Pages (fp)"},
    "lbl_fingerprint":      {"ru": "Fingerprint:", "en": "Fingerprint:"},
    "lbl_our_side":         {"ru": "Наша сторона:", "en": "Our side:"},
    "btn_send_review":      {"ru": "➡ Отправить в «Разбор»",
                             "en": "➡ Send to «Review»"},
    "err_file_not_found":   {"ru": "Исходный файл не найден в кэше. Перезапусти анализ.",
                             "en": "Source file not found in cache. Re-run analysis."},
    "hint_no_match_review": {"ru": "🔴 Документы со сбоем нельзя отправить в разбор.",
                             "en": "🔴 Failed documents cannot be sent to review."},

    # ── РАЗБОР И ПОДПИСАНИЕ (5_Avto_podpisanie.py) ───────────────────────
    "review_title":         {"ru": "🤖 Разбор и подписание",
                             "en": "🤖 Review & Sign"},
    "review_caption":       {"ru": "Загрузи договор — система найдёт места подписи. "
                                   "Дорисуй если нужно → скачай PDF.",
                             "en": "Upload a contract — the system will find signature spots. "
                                   "Add manually if needed → download PDF."},
    "warn_no_signature":    {"ru": "Подпись не загружена. Загрузите PNG подписи в Настройках (таб Подписант).",
                             "en": "No signature loaded. Upload signature PNG in Settings (Signatory tab)."},
    "lbl_current_doc":      {"ru": "📄 Текущий документ:", "en": "📄 Current document:"},
    "btn_new_doc":          {"ru": "📄 Загрузить договор", "en": "📄 Upload contract"},
    "uploader_label":       {"ru": "Загрузить договор",   "en": "Upload contract"},
    "status_analyzing":     {"ru": "Анализирую документ...", "en": "Analysing document..."},
    "step_parsing":         {"ru": "📄 Шаг 1: Парсинг...", "en": "📄 Step 1: Parsing..."},
    "step_parsed_ok":       {"ru": "✅ Страниц: {n}",      "en": "✅ Pages: {n}"},
    "err_parsing":          {"ru": "❌ Ошибка парсинга",   "en": "❌ Parsing error"},
    "step_language":        {"ru": "🌐 Шаг 2: Язык...",   "en": "🌐 Step 2: Language..."},
    "err_lang_unsupported": {"ru": "❌ Язык не поддерживается",
                             "en": "❌ Language not supported"},
    "err_lang_detail":      {"ru": "Поддерживаем ru/en/pl/mk. Определён: {lang}",
                             "en": "Supported: ru/en/pl/mk. Detected: {lang}"},
    "step_lang_ok":         {"ru": "✅ Язык: **{lang}**", "en": "✅ Language: **{lang}**"},
    "step_analysis":        {"ru": "🔎 Шаги 0–5: Анализ через signfinder-api...",
                             "en": "🔎 Steps 0–5: Analysing via signfinder-api..."},
    "err_doc_failed":       {"ru": "❌ Документ не обработан", "en": "❌ Document failed"},
    "err_doc_detail":       {"ru": "❌ Не удалось обработать документ: {err}",
                             "en": "❌ Failed to process document: {err}"},
    "step_green":           {"ru": "🟢 Применён шаблон «{name}» ({pct}%) · якорей: {n}",
                             "en": "🟢 Template «{name}» applied ({pct}%) · anchors: {n}"},
    "step_yellow":          {"ru": "🟡 Полный анализ · якорей: {n}",
                             "en": "🟡 Full analysis · anchors: {n}"},
    "step_no_anchors":      {"ru": "⚠️ Анализ завершён, мест подписи не найдено",
                             "en": "⚠️ Analysis done, no signature spots found"},
    "warn_api":             {"ru": "Предупреждение API: {msg}", "en": "API warning: {msg}"},
    "status_done":          {"ru": "✅ Готово",   "en": "✅ Done"},
    "status_err_analysis":  {"ru": "❌ Ошибка анализа", "en": "❌ Analysis error"},
    "err_analyze_api":      {"ru": "POST /v1/analyze: {err}", "en": "POST /v1/analyze: {err}"},
    "banner_green":         {"ru": "🟢 Шаблон «{name}» применён автоматически (совпадение {pct}%)",
                             "en": "🟢 Template «{name}» applied automatically (match {pct}%)"},
    "banner_yellow_side":   {"ru": "🟡 Полный анализ · {entity} / {signer}",
                             "en": "🟡 Full analysis · {entity} / {signer}"},
    "banner_yellow_no_tpl": {"ru": "🟡 Шаблонов не найдено — выполнен полный поиск",
                             "en": "🟡 No templates found — full search performed"},
    "btn_reanalyze":        {"ru": "🔄 Повторить анализ", "en": "🔄 Re-analyse"},
    "section_preview":      {"ru": "2️⃣ Превью и доразметка", "en": "2️⃣ Preview & markup"},
    "slider_scale":         {"ru": "Масштаб подписи (на весь документ)",
                             "en": "Signature scale (whole document)"},
    "slider_scale_help":    {"ru": "1.0 = 15мм высота (42pt). 0.5 = 7.5мм, 2.0 = 30мм. Применяется ко всем страницам.",
                             "en": "1.0 = 15mm height (42pt). 0.5 = 7.5mm, 2.0 = 30mm. Applies to all pages."},
    "lbl_anchors_on_page":  {"ru": "Места подписи на стр. {n}:", "en": "Signature spots on page {n}:"},
    "btn_all_on":           {"ru": "✅ Все",   "en": "✅ All"},
    "btn_all_off":          {"ru": "☐ Снять", "en": "☐ Deselect"},
    "lbl_no_anchors_page":  {"ru": "На стр. {n} мест подписи нет.",
                             "en": "No signature spots on page {n}."},
    "radio_canvas_mode":    {"ru": "Режим", "en": "Mode"},
    "mode_view":            {"ru": "👁 Просмотр / drag",         "en": "👁 View / drag"},
    "mode_add":             {"ru": "✏️ Добавить место подписи",  "en": "✏️ Add signature spot"},
    "lbl_page":             {"ru": "**Стр. {cur}** из {total}", "en": "**Page {cur}** of {total}"},
    "lbl_jump_to":          {"ru": "Перейти", "en": "Go to"},
    "warn_preview":         {"ru": "Превью недоступно: {err}", "en": "Preview unavailable: {err}"},
    "warn_no_text":         {"ru": "Нет текста в этой точке.", "en": "No text at this point."},
    "err_anchor_add":       {"ru": "Ошибка добавления якоря: {err}", "en": "Error adding anchor: {err}"},
    "lbl_manual_coords":    {"ru": "Ручной ввод координат:", "en": "Manual coordinates:"},
    "section_download":     {"ru": "7️⃣ Скачать подписанный PDF", "en": "7️⃣ Download signed PDF"},
    "caption_anchors_stat": {"ru": "{auto} auto + {manual} manual = {total} якорей · включено: {enabled}",
                             "en": "{auto} auto + {manual} manual = {total} anchors · enabled: {enabled}"},
    "warn_no_enabled":      {"ru": "Нет включённых мест подписи.", "en": "No signature spots enabled."},
    "caption_scale":        {"ru": "Масштаб подписи: **{scale}×** (меняется слайдером в разделе превью)",
                             "en": "Signature scale: **{scale}×** (change via slider in preview section)"},
    "btn_sign_download":    {"ru": "⬇ Подписать и скачать", "en": "⬇ Sign & download"},
    "err_signing":          {"ru": "Ошибка подписания: {err}", "en": "Signing error: {err}"},
    "btn_save_pdf":         {"ru": "💾 Сохранить PDF", "en": "💾 Save PDF"},
    "section_save_tpl":     {"ru": "💾 Сохранение шаблона", "en": "💾 Save template"},
    "lbl_tpl_name":         {"ru": "Имя шаблона", "en": "Template name"},
    "btn_save_tpl":         {"ru": "💾 Сохранить шаблон", "en": "💾 Save template"},
    "btn_save_tpl_manual":  {"ru": "💾 Сохранить шаблон (рекомендуется — есть ручные якоря)",
                             "en": "💾 Save template (recommended — manual anchors present)"},
    "info_tpl_manual":      {"ru": "Применённый шаблон был расширен ручными якорями. Что делать?",
                             "en": "Applied template was extended with manual anchors. What to do?"},
    "btn_update_tpl":       {"ru": "💾 Обновить существующий", "en": "💾 Update existing"},
    "btn_new_version":      {"ru": "🆕 Новая версия",          "en": "🆕 New version"},
    "btn_no_save":          {"ru": "✗ Не сохранять",           "en": "✗ Don't save"},
    "ok_tpl_updated":       {"ru": "Шаблон обновлён.",              "en": "Template updated."},
    "ok_tpl_new_ver":       {"ru": "Создана новая версия: {id}…",   "en": "New version created: {id}…"},
    "ok_tpl_saved":         {"ru": "Шаблон сохранён: `{name}` (id: {id}…)",
                             "en": "Template saved: `{name}` (id: {id}…)"},
    "err_tpl_save":         {"ru": "Ошибка сохранения шаблона: {err}", "en": "Template save error: {err}"},
    "dbg_export":           {"ru": "🔬 Диагностический экспорт", "en": "🔬 Diagnostic export"},
    "dbg_show_text":        {"ru": "📋 Показать как текст",      "en": "📋 Show as text"},
    "dbg_size":             {"ru": "Размер: {kb} KB",             "en": "Size: {kb} KB"},
    "dbg_download":         {"ru": "📥 Скачать JSON",             "en": "📥 Download JSON"},

    # ── АГЕНТ MAIL (6_Agent_Mail.py) ─────────────────────────────────────
    "agent_title":          {"ru": "📧 Агент Mail",     "en": "📧 Mail Agent"},
    "agent_timeout":        {"ru": "⏳ API занят — возможно идёт обработка писем. "
                                   "Нажмите «Обновить» через ~30 сек.",
                             "en": "⏳ API busy — possibly processing mail. "
                                   "Press «Refresh» in ~30 sec."},
    "agent_unavailable":    {"ru": "Агент недоступен: {err}", "en": "Agent unavailable: {err}"},
    "metric_status":        {"ru": "Статус",              "en": "Status"},
    "status_polling":       {"ru": "🔄 Идёт опрос…",     "en": "🔄 Polling…"},
    "status_ok":            {"ru": "🟢 Работает",         "en": "🟢 Running"},
    "status_no_imap":       {"ru": "⚠️ IMAP не настроен","en": "⚠️ IMAP not configured"},
    "metric_last_poll":     {"ru": "Последний опрос",     "en": "Last poll"},
    "metric_last_count":    {"ru": "Обработано (посл.)", "en": "Processed (last)"},
    "metric_queue":         {"ru": "В очереди",           "en": "In queue"},
    "info_polling":         {"ru": "🔄 Опрос идёт в фоне. Нажмите «Обновить» через ~30 сек, "
                                   "чтобы увидеть новые письма.",
                             "en": "🔄 Poll running in background. Press «Refresh» in ~30 sec "
                                   "to see new mail."},
    "info_imap_hint":       {"ru": "Настройте IMAP_HOST, IMAP_USER, IMAP_PASSWORD в `.env` "
                                   "и пересоберите агент.",
                             "en": "Set IMAP_HOST, IMAP_USER, IMAP_PASSWORD in `.env` "
                                   "and rebuild agent."},
    "tab_queue":            {"ru": "📋 Очередь разбора", "en": "📋 Review queue"},
    "tab_log":              {"ru": "📜 Журнал",           "en": "📜 Log"},
    "queue_title":          {"ru": "Письма, требующие проверки оператором",
                             "en": "Mail requiring operator review"},
    "btn_poll_now":         {"ru": "📨 Опросить почту сейчас", "en": "📨 Poll mail now"},
    "btn_refresh":          {"ru": "🔄 Обновить",              "en": "🔄 Refresh"},
    "err_poll":             {"ru": "Ошибка: {err}",            "en": "Error: {err}"},
    "warn_poll_running":    {"ru": "🔄 Опрос уже идёт — дождитесь завершения.",
                             "en": "🔄 Poll already running — wait for it to finish."},
    "info_poll_started":    {"ru": "⏳ Опрос запущен в фоне. Письма появятся по мере обработки — "
                                   "нажмите «Обновить» через ~30 сек.",
                             "en": "⏳ Poll started in background. Mail will appear as processed — "
                                   "press «Refresh» in ~30 sec."},
    "queue_empty":          {"ru": "Очередь пуста.", "en": "Queue is empty."},
    "lbl_no_subject":       {"ru": "(без темы)", "en": "(no subject)"},
    "lbl_from":             {"ru": "От:", "en": "From:"},
    "lbl_pdf_count":        {"ru": "PDF:", "en": "PDF:"},
    "btn_confirm":          {"ru": "✅ Подтвердить", "en": "✅ Confirm"},
    "btn_reject":           {"ru": "❌ Отклонить",   "en": "❌ Reject"},
    "btn_load":             {"ru": "📥 Загрузить",   "en": "📥 Load"},
    "btn_to_review":        {"ru": "✏️ В разбор",    "en": "✏️ To review"},
    "ok_confirm":           {"ru": "→ Green", "en": "→ Green"},
    "ok_reject":            {"ru": "→ Red",   "en": "→ Red"},
    "warn_no_originals":    {"ru": "⚠️ Оригиналы недоступны (старое письмо).",
                             "en": "⚠️ Originals unavailable (old mail)."},
    "lbl_resign":           {"ru": "Переразметить и переподписать вручную:",
                             "en": "Re-markup and re-sign manually:"},
    "log_title":            {"ru": "История обработки", "en": "Processing history"},
    "log_filter":           {"ru": "Фильтр",             "en": "Filter"},
    "log_filter_all":       {"ru": "все",                "en": "all"},
    "log_empty":            {"ru": "Журнал пуст.", "en": "Log is empty."},
    "col_time_log":         {"ru": "Время",   "en": "Time"},
    "col_subject":          {"ru": "Тема",    "en": "Subject"},
    "col_pdf":              {"ru": "PDF",     "en": "PDF"},
    "col_dest":             {"ru": "→ Папка", "en": "→ Folder"},

    # ── НАСТРОЙКИ (4_Nastroyki.py) ────────────────────────────────────────
    "settings_title":       {"ru": "⚙️ Настройки",   "en": "⚙️ Settings"},
    "tab_templates":        {"ru": "📄 Шаблоны",      "en": "📄 Templates"},
    "tab_prompts":          {"ru": "📝 Промпты",       "en": "📝 Prompts"},
    "tab_signer":           {"ru": "✍️ Подписант",    "en": "✍️ Signatory"},
    "tab_markers":          {"ru": "🏷 Маркеры",       "en": "🏷 Markers"},
    "tab_llm":              {"ru": "🤖 LLM",           "en": "🤖 LLM"},
    "tab_mail":             {"ru": "📧 Mail",           "en": "📧 Mail"},
    "tab_testing":          {"ru": "🧪 Тестирование",  "en": "🧪 Testing"},
}


def t(key: str, **kwargs) -> str:
    """Вернуть строку для текущего языка.

    Args:
        key: ключ из TRANSLATIONS
        **kwargs: подстановки для format(), например t("step_parsed_ok", n=5)

    Returns:
        Переведённая строка или ключ если перевод не найден.
    """
    lang = st.session_state.get("lang", "ru")
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key  # не нашли — вернуть ключ как fallback
    text = entry.get(lang) or entry.get("ru") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
