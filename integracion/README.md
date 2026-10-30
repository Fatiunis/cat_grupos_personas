# Integración y pruebas del flujo completo

APK → `POST /ingest` (FastAPI) → Postgres → pipeline de perfiles → dashboard.

## Levantar todo con datos llegando en vivo

```
cd integracion
docker compose up --build
```

- Dashboard: http://localhost:8000 (la pestaña Resumen se refresca sola cada 30 s).
- El servicio `simulador` arranca 40 teléfonos con 16 días de historia y después avanza
  un día simulado cada 30 s, con 2 personas nuevas por día. Lo que envía se ve con
  `docker compose logs -f simulador`.
- Postgres queda en `localhost:5432` (usuario, clave y base: `perfiles`).
- Se ajusta con un archivo `.env` junto al compose: `PERSONAS`, `HISTORIA`,
  `SEGUNDOS_POR_DIA`, `ALTAS_POR_DIA`, `INGEST_TOKEN`, `ADMIN_PASSWORD`.
- `docker compose down -v` apaga todo y borra la base.

## Pruebas

```
docker compose run --rm pruebas                  # contrato + end-to-end contra el compose
python -m pytest integracion/tests/test_contrato.py   # solo contrato, sin servidor
```

- `test_contrato.py` lee `DailySummary.kt` y `Categories.kt` y verifica que el simulador
  envía exactamente las mismas claves que la APK. Si se cambia la APK, falla hasta que se
  actualice `simulador/apk_resumen.py`.
- `test_e2e.py` prueba ingesta, reenvíos idempotentes, listas de días, días sin batería,
  campos nuevos, rechazo de malformados, token, conteos del dashboard y que el pipeline
  arma perfiles con lo que quedó en Postgres.

## Simulador

`simulador/dispositivo.py` genera eventos crudos como los de Android (pantalla,
desbloqueos, apps en primer plano, muestras de batería cada 15 min, notificaciones,
respuestas a la pregunta diaria) con 6 arquetipos. `simulador/apk_resumen.py` los resume
con el mismo cálculo que `DailySummary.kt`, y `simulador.py` imita a `DailyWorker`: cola
local, hasta 6 días atrás, reintento si no hay 2xx, días sin red y reenvíos de días ya
guardados.

```
python simulador/simulador.py --help
python simulador/simulador.py --personas 300 --historia 28 --salida enviados.jsonl   # sin servidor
```

`--con-arquetipo` agrega el arquetipo verdadero a cada día (solo para medir el ARI del
pipeline; la APK real no lo envía).
