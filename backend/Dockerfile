FROM python:3.11-slim

# Build deps for geopandas/pyproj. The raster stack (GDAL) is only needed when
# installing requirements-raster.txt or requirements-ml.txt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# REQUIREMENTS selects the dependency set:
#   requirements-core.txt    graph + simulation + API (default, no PyTorch)
#   requirements-raster.txt  adds rasterio/scikit-image (enables /simulate/flood)
#   requirements-ml.txt      adds PyTorch etc. (needed for ENABLE_ML=true)
ARG REQUIREMENTS=requirements-core.txt
COPY requirements*.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ${REQUIREMENTS}

COPY . .

# Data artifacts are NOT baked into the image; mount backend/data at runtime.
RUN mkdir -p data/rasters data/masks data/graphs data/sim_outputs data/cache data/checkpoints

# Segmentation router stays off unless the image was built with requirements-ml.txt.
ENV ENABLE_ML=false

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
