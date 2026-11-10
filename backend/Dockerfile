# Construir desde la raíz del repo (necesita ml/):
#   docker build -f backend/Dockerfile -t perfiles-backend .
FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY ml ml
COPY backend backend
WORKDIR /srv/backend
ENV PORT=8000
# Un hilo por librería numérica: en planes con poca CPU, muchos hilos se estorban y el análisis tarda minutos
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
