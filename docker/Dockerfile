# Используем официальный образ Python для лучшей переносимости
FROM python:3.10-slim

# Установка переменных окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя для безопасности
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/logs /app/data && \
    chown -R appuser:appuser /app

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование конфигурации
COPY config/ ./config/

# Копирование исходного кода
COPY --chown=appuser:appuser src/ ./src/

# Копирование шаблонов и статики
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser static/ ./static/

# Переключение на непривилегированного пользователя
USER appuser

# Экспорт порта для веб-сервера
EXPOSE 5000

# Healthcheck для мониторинга
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app/src'); import requests; requests.get('http://localhost:5000/api/stats', timeout=5)" || exit 1

# Команда запуска
WORKDIR /app/src
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]

