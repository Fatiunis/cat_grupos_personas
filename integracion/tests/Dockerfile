# Corre las pruebas de contrato y end-to-end contra el backend y Postgres del compose
FROM python:3.12-slim
WORKDIR /repo
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt numpy tzdata pytest "psycopg[binary]" requests
COPY android android
COPY ml ml
COPY integracion integracion
ENTRYPOINT ["pytest", "-v", "integracion/tests"]
