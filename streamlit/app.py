"""SignFinder MVP — Dashboard"""
import streamlit as st
from core.auth import check_access_code
from core.i18n import t

st.set_page_config(page_title="SignFinder", page_icon="🤖", layout="wide")

st.markdown("""
<style>
  [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
  [data-testid="stDecoration"] {display: none;}
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ── ЯЗЫК ──────────────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state["lang"] = "ru"

# ── AUTH ──────────────────────────────────────────────────────────────────────
if "auth" not in st.session_state:
    st.session_state["auth"] = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if not st.session_state["auth"]:
    st.title(t("app_title"))

    lang_col1, lang_col2, _ = st.columns([1, 1, 6])
    with lang_col1:
        if st.button("🇷🇺 RU", use_container_width=True,
                     type="primary" if st.session_state["lang"] == "ru" else "secondary"):
            st.session_state["lang"] = "ru"
            st.rerun()
    with lang_col2:
        if st.button("🇬🇧 EN", use_container_width=True,
                     type="primary" if st.session_state["lang"] == "en" else "secondary"):
            st.session_state["lang"] = "en"
            st.rerun()

    code = st.text_input(t("access_code"), type="password")
    if st.button(t("btn_login")):
        if check_access_code(code):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error(t("err_wrong_code"))
    st.stop()

# ── НАВИГАЦИЯ ─────────────────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("views/5_Avto_podpisanie.py", title=t("nav_review")),
    st.Page("views/3_Paket.py",           title=t("nav_batch")),
    st.Page("views/6_Agent_Mail.py",      title=t("nav_agent")),
    st.Page("views/4_Nastroyki.py",       title=t("nav_settings")),
])
pg.run()
