FROM python:3.11-slim

# LibreOffice для DOCX→PDF + шрифты кириллицы
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Context теперь C:\work\ — пути относительно workspace root
COPY streamlit/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# signfinder-core — из локальных исходников (не из GitHub)
COPY signfinder-core/ /tmp/signfinder-core/
RUN pip install --no-cache-dir /tmp/signfinder-core/

# Код Streamlit-приложения
COPY streamlit/ .

# Тесты signfinder-core для запуска через test_runner
COPY signfinder-core/tests/ /app/sf_tests/

# config/ монтируется как volume — создаём пустую директорию
RUN mkdir -p /app/config

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--server.enableCORS=false", \
    "--server.enableXsrfProtection=false", \
    "--browser.serverAddress=localhost", \
    "--browser.serverPort=8501"]
