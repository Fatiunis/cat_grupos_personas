"""El simulador manda exactamente las mismas claves que DailySummary.kt.

Si alguien agrega o renombra un campo en la APK, esta prueba falla hasta que se
actualice el simulador (y se revise que el backend y el pipeline lo esperan).
"""
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "integracion" / "simulador"))
KT = RAIZ / "android" / "app" / "src" / "main" / "java" / "com" / "perfiles" / "uso"

import apk_resumen  # noqa: E402
from dispositivo import nueva_persona  # noqa: E402


def claves_kotlin():
    fuente = (KT / "DailySummary.kt").read_text()
    claves = set(re.findall(r'\.put\("([a-z0-9_]+)"', fuente))
    categorias = re.search(r"val ALL = listOf\(([^)]*)\)", (KT / "Categories.kt").read_text()).group(1)
    cats = re.findall(r'"([a-z]+)"', categorias)
    assert '"${c}_min"' in fuente
    return claves | {f"{c}_min" for c in cats}, cats


def payload_simulado(consiente_notif=True):
    zona = ZoneInfo("America/Bogota")
    alta = datetime(2026, 3, 1, tzinfo=zona)
    p = nueva_persona(np.random.default_rng(3), zona, alta)
    p.tel.consiente_notificaciones = consiente_notif
    for i in range(3):
        p.vivir_dia(alta + timedelta(days=i))
    return apk_resumen.resumen_diario(p.tel, date(2026, 3, 2))


def test_mismas_categorias():
    _, cats = claves_kotlin()
    assert cats == apk_resumen.CATEGORIAS


def test_mismas_claves_que_la_apk():
    esperadas, _ = claves_kotlin()
    assert set(payload_simulado()) == esperadas


def test_sin_consentimiento_no_va_notificaciones():
    assert "notificaciones" not in payload_simulado(consiente_notif=False)


def test_tipos():
    p = payload_simulado()
    assert isinstance(p["bloqueo_pantalla"], bool)
    assert isinstance(p["desbloqueos"], int)
    assert p["q_cumplimiento"] is None or 1 <= p["q_cumplimiento"] <= 5
    assert p["q_puntual"] in (None, "si", "no", "na")
    date.fromisoformat(p["fecha"])
