FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY price-api/mock_price_api.py ./price-api/mock_price_api.py
COPY seeds/price_catalog.json ./seeds/price_catalog.json
CMD ["python", "price-api/mock_price_api.py", "--host", "0.0.0.0", "--port", "8099"]
