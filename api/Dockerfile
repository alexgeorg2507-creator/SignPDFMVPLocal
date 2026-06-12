FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY signfinder-core/ /tmp/signfinder-core/
RUN pip install --no-cache-dir /tmp/signfinder-core/

RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.32" \
    "python-multipart>=0.0.12" \
    "httpx>=0.27" \
    "pydantic>=2.5" \
    "pytest>=7.4"

COPY signfinder-core/tests/ /app/sf_tests/
COPY signfinder-api/app/ ./app/

ENV PORT=8000
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
