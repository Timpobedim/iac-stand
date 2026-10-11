# Образ сервиса заказов. Процесс работает не от root; проверка здоровья встроена в образ,
# чтобы ею пользовались и Ansible при выкате, и docker ps.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --no-create-home orders
COPY orders ./orders

USER 10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "orders.main:build", "--factory", "--host", "0.0.0.0", "--port", "8000"]
