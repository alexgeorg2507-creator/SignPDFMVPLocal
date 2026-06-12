FROM python:3.11-slim

# LibreOffice для DOCX→PDF (агент конвертирует сам, как streamlit)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    fonts-dejavu \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Слой 1: signfinder-core из COPY (идентично api/Dockerfile)
COPY signfinder-core/ /tmp/signfinder-core/
RUN pip install --no-cache-dir /tmp/signfinder-core/

# Слой 2: зависимости агента
COPY SignPDFMVPLocal/agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Слой 3: код агента
COPY SignPDFMVPLocal/agent/app/ ./app/

ENV PORT=9000
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
