# Hallazgos de integración y QA (2026-10-30)

Probado con el simulador de `integracion/simulador` (rama `claude/project-thread-lz0nxc`): genera eventos crudos de UsageStatsManager, batería y notificaciones, y los resume con una copia línea a línea de `DailySummary.kt`. 600 teléfonos x 28 días en formato APK; el pipeline (94cecf9) llega a ARI 0,956 contra los arquetipos.

## APK (hilo APK/pipeline)

1. **Corte del día a medianoche (importante).** `hora_inicio_sueno` sale 0.0 en el 54% de los días: quien se duerme antes de las 00:00 tiene su mayor hueco desde las 00:00 hasta que despierta. `hora_ultimo_uso` nunca pasa de 24.0 (un nocturno que usa hasta las 3:00 registra 23.9). `hora_primer_uso` queda en 0.x para quien usa después de medianoche (media 4,1 h frente a mediana 6,3 h). Una sesión que empezó antes de las 00:00 se pierde del día siguiente (llega NON_INTERACTIVE sin INTERACTIVE). `synthetic.py` asume "día despierto" (último uso 0.8 o 3.0, sueño = último uso + 0,1-0,6 h), así que el pipeline está validado con datos que la APK no produce. Sugerencia: consultar eventos en una ventana más amplia (18:00 del día anterior a 14:00 del siguiente) y definir sueño = mayor hueco de al menos 4 h que empiece entre 18:00 y 06:00; último uso = fin de la sesión antes de ese hueco; primer uso = primera sesión después del hueco de la noche anterior.
2. **Retiro.** `Store.wipe()` no avisa al servidor, pero el consentimiento dice "tus datos se borran". Hace falta un aviso de retiro al backend o cambiar el texto.
3. **Código de participante.** La app muestra `participantId.take(8)` y el JSON lleva el UUID completo; el cruce con el BFI-2 tiene que ser por prefijo. Mostrar el código completo o enviar también el corto.
4. **Timeouts.** `HttpURLConnection` sin `connectTimeout`/`readTimeout`; con Render dormido (arranque de ~50 s) conviene fijarlos (p. ej. 30 s / 90 s).
5. **URL y token vacíos.** `INGEST_URL` e `INGEST_TOKEN` están fijos en "" en `build.gradle.kts`, así que la APK del CI no envía nada. Leerlos de una propiedad de Gradle o de secretos de GitHub Actions.

## Pipeline (hilo APK/pipeline)

6. `limpiar()` descarta los días sin muestras de batería (`bateria_min_pct` NaN no pasa `between`). Con 10% de días sin BatteryWorker se perdió el 10% de los días (16.754 → 15.038). Sugerencia: `d.bateria_min_pct.isna() | d.bateria_min_pct.between(0, 100)`.
7. Entran como features `q_cumplimiento` (es la etiqueta, contamina el clustering), `version_android` y `almacenamiento_libre_pct` (del dispositivo, no del comportamiento). Sugerencia: excluir `q_*` y `version_android`.

Estado: los 7 puntos anteriores quedaron corregidos en eb28a90 (APK) y el simulador ya usa el nuevo cálculo de horarios (ventana 05:00 a 05:00). Con 600 teléfonos x 29 días el pipeline da ARI 0,897 y los horarios nocturnos salen bien (último uso mediano del arquetipo nocturno: 27,2 h).

8. **Pipeline (nuevo): una columna vacía rompe la corrida.** Si un campo existe solo en personas que no llegan a 14 días (p. ej. `pasos` enviado por una versión nueva de la app a alguien que recién se unió), tras filtrar queda toda en NaN, `fillna(median)` no la llena y PCA falla con "Input X contains NaN". Pasó en el compose: la corrida desde el dashboard termina en error. Sugerencia: en `features_por_persona`, `feats = feats.dropna(axis=1, how="all")` antes del `fillna`.

## Backend (hilo backend + dashboard), PR #2 en 5db5c78

Corrido con docker-compose (Postgres 16) y el simulador: 21 de 23 pruebas pasan, incluidas ingesta, reenvíos idempotentes, listas de días, 16 envíos simultáneos del mismo participante, días sin batería, campos nuevos, malformados (422), token de ingesta, retiro con DELETE (204 y luego 404), token del retiro, clave del dashboard y conteos en vivo de `/api/resumen`.

Estado: 8 corregido en 2ac2f98; 9 y 10 en c0f7947 (422 para ids inválidos, 410 para envíos de personas retiradas); 11 en 6bf5d81. Con 6bf5d81 pasan las 24 pruebas.

11. **ARI con arquetipos parciales.** Si solo algunos participantes traen `arquetipo` (datos sintéticos cargados con `cargar_sinteticos.py` y después datos reales), `analisis.py:147` deja NaN en `verdad` y la corrida falla con "Input contains NaN". Sugerencia: calcular el ARI solo sobre `verdad.notna()`.

9. **Error 500 con ids inesperados.** `participante_id` de más de 64 caracteres da `StringDataRightTruncation` y uno numérico (`12345`) da `operator does not exist: character varying = integer`; los dos responden 500. Sugerencia: validar que sea texto de 1 a 64 caracteres y responder 422.
10. **Retiro con envío en curso (menor).** Si DailyWorker está subiendo un día justo cuando la persona se retira, ese día puede llegar después del DELETE y recrear al participante. Se puede guardar una lista de ids retirados y rechazar sus envíos con 410, o borrar también al recibir días de un id retirado.
