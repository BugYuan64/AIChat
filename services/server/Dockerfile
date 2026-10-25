FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY aichat ./aichat
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 aichat
USER aichat

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "aichat.app:app", "--host", "0.0.0.0", "--port", "8000"]
