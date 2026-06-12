"""SignFinder MVP v1.10.1 — Dashboard"""
import streamlit as st

from core.auth import check_access_code

st.set_page_config(page_title="SignFinder MVP", page_icon="🤖", layout="wide")

# Убираем технический тулбар Streamlit (Deploy + меню «⋮») в правом верхнем углу.
st.markdown(
    """
    <style>
      [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
      [data-testid="stDecoration"] {display: none;}
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# Явная навигация — _9_Testirovanie убрана из меню
pg = st.navigation(
    [
        st.Page("views/3_Paket.py",              title="📦 Пакетная обработка"),
        st.Page("views/4_Nastroyki.py",          title="⚙️ Настройки"),
        st.Page("views/5_Avto_podpisanie.py",    title="✍️ Разбор и подписание"),
        st.Page("views/6_Agent_Mail.py",         title="📧 Агент Mail"),
    ]
)


# ── ENV: загружаем .env для локальной разработки ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv опционален; в Cloud Run env задаётся через секреты


# ── AUTH GATE ─────────────────────────────────────────────────────────────────
if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    st.title("🔐 SignFinder MVP")
    code = st.text_input("Код доступа", type="password")
    if st.button("Войти"):
        if check_access_code(code):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Неверный код")
    st.stop()

pg.run()
