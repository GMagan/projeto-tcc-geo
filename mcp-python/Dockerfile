# As rodas (wheels) de geopandas, pyogrio e rasterio já trazem GDAL, GEOS e PROJ
# compilados; por isso a imagem não instala gdal-bin nem compilador.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app/mcp-python

COPY mcp-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-python/ /app/mcp-python/
# dados, base de conhecimento e resultados entram por volume (ver docker-compose.yml)

RUN useradd --create-home geo && mkdir -p /app/resultados && chown -R geo /app
USER geo

EXPOSE 8001
CMD ["python", "server.py"]
