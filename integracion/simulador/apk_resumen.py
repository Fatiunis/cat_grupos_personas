"""Copia en Python del cálculo de DailySummary.kt (versión de eb28a90) y Workers.kt (BatteryWorker).

Recibe los mismos insumos que tiene la APK en el teléfono (eventos de UsageStatsManager,
muestras de batería cada 15 min, horas de notificaciones, apps instaladas) y arma el
mismo JSON diario. Se mantiene línea por línea con el código Kotlin a propósito: si la
APK calcula algo raro, el simulador también, y así las pruebas lo detectan.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Tipos de UsageEvents.Event usados por la APK
ACTIVITY_RESUMED = 1
ACTIVITY_PAUSED = 2
SCREEN_INTERACTIVE = 15
SCREEN_NON_INTERACTIVE = 16
KEYGUARD_HIDDEN = 18

CATEGORIAS = ["social", "mensajeria", "juegos", "video", "productividad", "educacion", "finanzas", "compras", "otros"]


@dataclass
class Telefono:
    """Lo que la APK puede leer del teléfono."""
    participante_id: str
    zona: ZoneInfo
    eventos: list = field(default_factory=list)        # (ts_ms, tipo, paquete)
    bateria: list = field(default_factory=list)        # (ts_ms, nivel, enchufado, red)
    notificaciones: list = field(default_factory=list)  # ts_ms
    apps: list = field(default_factory=list)           # (paquete, first_install_ms)
    categoria_de: dict = field(default_factory=dict)   # paquete -> categoría (Categories.of)
    consiente_notificaciones: bool = True
    respuestas: dict = field(default_factory=dict)     # fecha -> (cumplimiento, puntual)
    version_app: str = "0.1.0"
    modelo: str = "Samsung SM-A155M"
    version_android: int = 34
    almacenamiento_libre_pct: float = 40.0
    bloqueo_pantalla: bool = True
    parche_seguridad: str = "2026-08-01"


def round1(x):
    # Math.round de Java redondea .5 hacia arriba, no al par
    import math
    return math.floor(x * 10 + 0.5) / 10.0


def _ms(d, hora, zona):
    return int(datetime(d.year, d.month, d.day, tzinfo=zona).replace(hour=hora).timestamp() * 1000)


DAY_START_HOUR = 5


def resumen_diario(t: Telefono, d: date) -> dict:
    """El día va de las 05:00 de `d` a las 05:00 del siguiente; horas desde la medianoche de `d`."""
    zona = t.zona
    d1 = d + timedelta(days=1)
    midnight = _ms(d, 0, zona)
    start, end = _ms(d, DAY_START_HOUR, zona), _ms(d1, DAY_START_HOUR, zona)
    out = {
        "participante_id": t.participante_id,
        "fecha": d.isoformat(),
        "version_app": t.version_app,
        "modelo_telefono": t.modelo,
        "version_android": t.version_android,
    }
    _uso(t, midnight, start, end, out)
    _sueno(t, d, midnight, out)
    _bateria(t, midnight, start, end, out)
    _dispositivo(t, start, end, out)
    if t.consiente_notificaciones:
        out["notificaciones"] = sum(1 for ts in t.notificaciones if start <= ts < end)
    c, p = t.respuestas.get(d, (None, None))
    out["q_cumplimiento"] = c
    out["q_puntual"] = p
    return out


def _horas(midnight, ts):
    return (ts - midnight) / 3_600_000.0


def _leer_pantalla(t, desde, hasta):
    # usm.queryEvents(from, to) solo devuelve eventos dentro del intervalo
    sesiones, screen_on, unlocks, fg_start, cat_ms = [], None, 0, {}, {}
    for ts, tipo, pkg in (e for e in t.eventos if desde <= e[0] < hasta):
        if tipo == SCREEN_INTERACTIVE:
            screen_on = ts
        elif tipo == SCREEN_NON_INTERACTIVE:
            if screen_on is not None:
                sesiones.append((screen_on, ts))
            screen_on = None
        elif tipo == KEYGUARD_HIDDEN:
            unlocks += 1
        elif tipo == ACTIVITY_RESUMED:
            fg_start[pkg] = ts
        elif tipo == ACTIVITY_PAUSED:
            s = fg_start.pop(pkg, None)
            if s is not None:
                cat = t.categoria_de.get(pkg, "otros")
                cat_ms[cat] = cat_ms.get(cat, 0) + (ts - s)
    if screen_on is not None:
        sesiones.append((screen_on, hasta))
    return sesiones, unlocks, cat_ms


def _uso(t, midnight, start, end, out):
    sesiones, unlocks, cat_ms = _leer_pantalla(t, start, end)
    screen_min = sum(b - a for a, b in sesiones) / 60000.0
    out["pantalla_min"] = round1(screen_min)
    out["desbloqueos"] = unlocks
    out["sesion_media_min"] = 0.0 if not sesiones else round1(screen_min / len(sesiones))
    out["sesiones_cortas"] = sum(1 for a, b in sesiones if b - a < 30_000)
    out["hora_primer_uso"] = round1(_horas(midnight, sesiones[0][0])) if sesiones else None
    out["hora_ultimo_uso"] = round1(_horas(midnight, sesiones[-1][1])) if sesiones else None
    night_start = midnight + 24 * 3_600_000
    night_ms = sum(max(0, min(b, end) - max(a, night_start)) for a, b in sesiones)
    out["uso_nocturno_min"] = round1(night_ms / 60000.0)
    for c in CATEGORIAS:
        out[f"{c}_min"] = round1(cat_ms.get(c, 0) / 60000.0)


def _sueno(t, d, midnight, out):
    desde, hasta = _ms(d, 18, t.zona), _ms(d + timedelta(days=1), 14, t.zona)
    best_gap, best_start, prev_end = 0, desde, desde
    for a, b in _leer_pantalla(t, desde, hasta)[0] + [(hasta, hasta)]:
        gap = a - prev_end
        if gap > best_gap:
            best_gap, best_start = gap, prev_end
        prev_end = max(prev_end, b)
    out["hora_inicio_sueno"] = round1(_horas(midnight, best_start)) if best_gap >= 4 * 3_600_000 else None


def _bateria(t, midnight, start, end, out):
    filas = [r for r in t.bateria if start <= r[0] < end]
    if not filas:
        return
    niveles = [r[1] for r in filas]
    out["bateria_min_pct"] = min(niveles)
    out["veces_bateria_baja"] = sum(1 for a, b in zip(niveles, niveles[1:]) if a >= 15 and b < 15)
    enchufado = [r[2] for r in filas]
    out["cargas"] = sum(1 for a, b in zip(enchufado, enchufado[1:]) if not a and b)
    out["carga_nocturna"] = 1 if any(r[2] and _horas(midnight, r[0]) >= 22 for r in filas) else 0
    out["wifi_min"] = sum(1 for r in filas if r[3] == "wifi") * 15
    out["datos_moviles_min"] = sum(1 for r in filas if r[3] == "movil") * 15


def _dispositivo(t, start, end, out):
    out["apps_instaladas"] = len(t.apps)
    out["apps_nuevas"] = sum(1 for _, inst in t.apps if start <= inst < end)
    out["almacenamiento_libre_pct"] = round1(t.almacenamiento_libre_pct)
    out["bloqueo_pantalla"] = t.bloqueo_pantalla
    out["parche_seguridad"] = t.parche_seguridad
