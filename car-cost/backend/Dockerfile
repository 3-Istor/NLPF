FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Le chargeur existant émet du COPY : psql l’exécute sans réinterprétation.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY seeds/ ./seeds/
ENTRYPOINT ["python", "-m", "carcost.infrastructure.startup"]
CMD ["uvicorn", "carcost.infrastructure.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
