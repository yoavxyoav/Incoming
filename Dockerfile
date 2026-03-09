FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv --no-cache-dir

COPY pyproject.toml .
RUN uv pip install --system --no-cache ".[notify,mqtt]"

COPY app/ ./app/
COPY frontend/ ./frontend/

RUN mkdir -p logs data

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
