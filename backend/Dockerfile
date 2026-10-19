FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "python -m scripts.seed_data && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
