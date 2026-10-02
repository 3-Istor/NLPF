FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY price-api/mock_price_api.py price-api/simulation.py ./price-api/
COPY price-api/data ./price-api/data
# Les catalogues des quatre nomenclatures : le Multipla, puis les trois Valhalla.
COPY seeds/price_catalog.json ./seeds/price_catalog.json
COPY seeds/valhalla ./seeds/valhalla
# Une année de marché simulée en 40 minutes ; `--year-minutes 0` fige les prix.
CMD ["python", "price-api/mock_price_api.py", "--host", "0.0.0.0", "--port", "8099", "--year-minutes", "40"]
