# --- Базовый образ ---
FROM python:3.12-slim AS base

# Не создавать .pyc-файлы и не буферизовать stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# Минимальный набор системных утилит.
# curl нужен для healthcheck, ca-certificates — для HTTPS-запросов
# (NeuralDeep, MCP-серверы, скачивание колёс).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- uv / uvx ---
# Копируем бинарники из официального образа — это быстрее,
# чем ставить uv через pip, и гарантирует наличие uvx.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# --- Зависимости приложения ---
WORKDIR /app

# Копируем только requirements — это позволяет кэшировать слой,
# пока код не меняется.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Исходники ---
COPY . .

# --- Пользователь без root ---
# В целях безопасности создаём непривилегированного пользователя.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# --- Порт ---
# Amvera ожидает, что приложение слушает containerPort из amvera.yml.
EXPOSE 80

# --- Запуск ---
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]