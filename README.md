# Perfiles de uso de teléfonos Android

Trabajo académico: recolectar métricas agregadas de uso del teléfono (con consentimiento) y agrupar a las personas en perfiles.

## android/

Prototipo de la APK en Kotlin (minSdk 28, Jetpack Compose, WorkManager).

- Consentimiento con casilla opcional para contar notificaciones, guía de permisos (acceso a datos de uso, batería, notificaciones), pregunta diaria (cumplimiento del plan 1-5 y puntualidad) con recordatorio a las 21:00, vista de lo que se envía, pausa y retiro con borrado.
- `DailySummary.kt` resume cada día en el teléfono: pantalla, desbloqueos, sesiones, horarios, uso nocturno, inicio de sueño, minutos por categoría, batería, cargas, red, apps, almacenamiento, bloqueo y parche de seguridad.
- Un día va de 05:00 a 05:00 y las horas son continuas desde la medianoche (25.5 = 01:30 del día siguiente). El inicio de sueño se busca entre las 18:00 y las 14:00 del día siguiente, por eso cada día se envía después de las 15:00 del día siguiente.
- Al retirarse, la app borra lo local y envía `DELETE <base>/participantes/<id>` al servidor.
- `INGEST_URL` e `INGEST_TOKEN` se pasan al compilar (`-PingestUrl=... -PingestToken=...`); en CI salen de los secretos del repositorio con esos nombres.
- `BatteryWorker` toma una muestra cada 15 min; `DailyWorker` arma los resúmenes pendientes y los envía a `INGEST_URL` (vacío = solo local).
- Pendiente para la v2: pasos y lugares distintos (ubicación aproximada), y el backend de ingesta.

La APK la compila GitHub Actions (`.github/workflows/android.yml`) y queda como artefacto descargable del flujo.

## ml/

- `synthetic.py`: genera datos diarios sintéticos con 6 arquetipos y una etiqueta BFI-2 sintética.
- `pipeline.py`: limpia, calcula features por persona (mínimo 14 días), reduce con PCA, elige el número de perfiles con BIC y estabilidad, agrupa con mezcla gaussiana, entrena un clasificador de asignación y compara los perfiles con la etiqueta.

```
pip install -r ml/requirements.txt
cd ml
python synthetic.py --personas 1500
python pipeline.py --etiquetas etiquetas_sinteticas.csv
```

Los datos sintéticos solo prueban el pipeline; el modelo final se entrena con datos reales.

## Resultado con datos sintéticos (2026-10-30)

Con 1.500 personas y dos semillas distintas, el pipeline recupera los arquetipos plantados con ARI de 0,85 y 0,94 (meta 0,7). La regla automática tiende a elegir más perfiles de los plantados (divide un arquetipo en dos), así que con datos reales hay que revisar la tabla de selección y fijar `--k`.

## backend/

API FastAPI y dashboard web. Recibe los resúmenes diarios de la APK, guarda los datos y corre el pipeline de `ml/` desde la interfaz.

- `POST /ingest`: un objeto (o una lista) por persona y día, igual al JSON de `DailySummary.kt`. Un reenvío del mismo día lo reemplaza. Si `INGEST_TOKEN` está definido, exige `Authorization: Bearer <token>`.
- Dashboard en `/`, con cuatro vistas:
  - **Resumen**: recolección en vivo, se refresca cada 30 s.
  - **Participantes**: búsqueda, detalle por persona, excluir del análisis, notas, BFI-2 y borrado por retiro.
  - **Perfiles**: tarjetas con nombre editable, mapa PCA, BFI-2 por perfil y tabla de rasgos.
  - **Análisis**: correr el pipeline con k automático o fijo, subir el CSV del BFI-2 y exportar a CSV.
- Variables de entorno: `DATABASE_URL` (PostgreSQL; vacío = SQLite local), `INGEST_TOKEN`, `ADMIN_USER` y `ADMIN_PASSWORD` (vacío = dashboard sin clave, solo para uso local).

Prueba local con datos sintéticos:

```
pip install -r backend/requirements.txt
cd backend
python cargar_sinteticos.py --personas 400 --corrida
uvicorn app.main:app --reload    # abrir http://localhost:8000
python -m pytest tests
```

Despliegue sugerido, sin costo: PostgreSQL en [Neon](https://neon.tech) (plan gratuito de 0,5 GB; 200 personas por 2 meses ocupan unos 12 MB) y el backend en [Render](https://render.com) con `render.yaml`. El plan gratuito de Render se duerme tras 15 min sin tráfico; la APK reintenta, así que no se pierden días. Después se ponen `INGEST_URL` (`https://<servicio>.onrender.com/ingest`) e `INGEST_TOKEN` (el mismo valor del servidor) en `android/app/build.gradle.kts` y se vuelve a compilar la APK.
