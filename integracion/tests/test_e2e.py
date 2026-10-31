"""Pruebas de punta a punta: teléfonos simulados -> /ingest -> Postgres -> API -> pipeline.

Necesitan el backend corriendo; con el compose: docker compose run --rm pruebas
Variables: BACKEND_URL, INGEST_URL, INGEST_TOKEN, ADMIN_PASSWORD, DATABASE_URL.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd
import pytest
import requests

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = os.environ.get("BACKEND_URL", "").rstrip("/")
INGEST = os.environ.get("INGEST_URL") or (BACKEND + "/ingest")
TOKEN = os.environ.get("INGEST_TOKEN", "")
ADMIN = os.environ.get("ADMIN_PASSWORD", "")
DB = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(not BACKEND, reason="sin BACKEND_URL: el backend no está corriendo")


def post(payload, token=TOKEN):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(INGEST, json=payload, headers=h, timeout=30)


def api(ruta):
    auth = ("admin", ADMIN) if ADMIN else None
    r = requests.get(BACKEND + ruta, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def dia(pid, fecha="2026-03-02", **extra):
    base = json.loads((Path(__file__).parent / "payload_ejemplo.json").read_text())
    base.update(participante_id=pid, fecha=fecha, **extra)
    return base


def participante(pid):
    filas = api("/api/participantes")
    return next((f for f in filas if f["id"] == pid), None)


def dias_en_db(pid):
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DB.replace("postgresql+psycopg://", "postgresql://")) as c:
        return c.execute("select count(*) from dias where participante_id = %s", (pid,)).fetchone()[0]


def test_salud():
    assert requests.get(BACKEND + "/salud", timeout=10).status_code == 200


def test_ingesta_guarda_un_dia():
    pid = str(uuid.uuid4())
    r = post(dia(pid))
    assert r.status_code == 200, r.text
    p = participante(pid)
    assert p is not None and p["dias"] == 1


def test_reenvio_es_idempotente():
    """La APK reenvía si no recibe 2xx; el mismo día no debe duplicarse."""
    pid = str(uuid.uuid4())
    assert post(dia(pid, pantalla_min=100.0)).status_code == 200
    assert post(dia(pid, pantalla_min=200.0)).status_code == 200
    assert participante(pid)["dias"] == 1
    if DB:
        assert dias_en_db(pid) == 1


def test_lista_de_dias():
    pid = str(uuid.uuid4())
    r = post([dia(pid, "2026-03-02"), dia(pid, "2026-03-03")])
    assert r.status_code == 200, r.text
    assert participante(pid)["dias"] == 2


def test_dia_sin_bateria_ni_notificaciones():
    """Sin muestras de BatteryWorker y sin consentimiento de notificaciones faltan esas claves."""
    pid = str(uuid.uuid4())
    p = dia(pid)
    for k in ["bateria_min_pct", "veces_bateria_baja", "cargas", "carga_nocturna", "wifi_min",
              "datos_moviles_min", "notificaciones"]:
        p.pop(k)
    p.update(q_cumplimiento=None, q_puntual=None, hora_inicio_sueno=None)
    assert post(p).status_code == 200


def test_campo_nuevo_de_otra_version_de_la_app():
    pid = str(uuid.uuid4())
    assert post(dia(pid, version_app="0.2.0", pasos=5400)).status_code == 200


@pytest.mark.parametrize("payload", [
    {"fecha": "2026-03-02", "pantalla_min": 10},
    {"participante_id": "x", "pantalla_min": 10},
    {"participante_id": "x", "fecha": "2026-13-45"},
    "esto no es un objeto",
])
def test_rechaza_malformados(payload):
    assert 400 <= post(payload).status_code < 500


@pytest.mark.parametrize("pid", ["x" * 200, 12345])
def test_id_raro_no_da_500(pid):
    """Un id inesperado debe rechazarse con 4xx o guardarse, nunca romper el servidor."""
    assert post(dia(pid)).status_code < 500


def test_lista_con_un_dia_malo_no_guarda_nada():
    pid = str(uuid.uuid4())
    assert post([dia(pid), {"participante_id": pid}]).status_code == 422
    assert participante(pid) is None


def test_reenvios_simultaneos():
    """Dos teléfonos nuevos que envían a la vez (o un reintento solapado) no deben dar 500."""
    from concurrent.futures import ThreadPoolExecutor
    pid = str(uuid.uuid4())
    with ThreadPoolExecutor(8) as ex:
        codigos = list(ex.map(lambda i: post(dia(pid, f"2026-03-{i % 3 + 1:02d}")).status_code, range(16)))
    assert all(c == 200 for c in codigos), codigos
    assert participante(pid)["dias"] == 3


def retiro(pid, token=TOKEN):
    """Lo que hace WithdrawWorker: DELETE <INGEST_URL sin /ingest>/participantes/<id>."""
    base = INGEST.rstrip("/").removesuffix("/ingest")
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.delete(f"{base}/participantes/{pid}", headers=h, timeout=30)


def test_retiro_borra_todo_y_es_reintentable():
    pid = str(uuid.uuid4())
    assert post([dia(pid, "2026-03-02"), dia(pid, "2026-03-03")]).status_code == 200
    r = retiro(pid)
    assert 200 <= r.status_code < 300, r.text
    assert participante(pid) is None
    if DB:
        assert dias_en_db(pid) == 0
    assert retiro(pid).status_code == 404  # la APK lo toma como éxito y deja de reintentar
    # Un día que estaba subiéndose cuando la persona se retiró no recrea al participante
    assert post(dia(pid, "2026-03-04")).status_code == 410
    assert participante(pid) is None


@pytest.mark.skipif(not TOKEN, reason="INGEST_TOKEN no definido")
def test_retiro_exige_token():
    pid = str(uuid.uuid4())
    assert post(dia(pid)).status_code == 200
    assert retiro(pid, token="").status_code in (401, 403)
    assert participante(pid) is not None


@pytest.mark.skipif(not TOKEN, reason="INGEST_TOKEN no definido")
def test_exige_token():
    assert post(dia(str(uuid.uuid4())), token="").status_code in (401, 403)
    assert post(dia(str(uuid.uuid4())), token="malo").status_code in (401, 403)


def test_simulador_completo_y_resumen(tmp_path):
    """20 teléfonos con 16 días de historia, con cortes de red y reenvíos, llegan completos."""
    antes = api("/api/resumen")
    salida = tmp_path / "enviados.jsonl"
    subprocess.run([sys.executable, str(RAIZ / "integracion/simulador/simulador.py"), "--url", INGEST,
                    "--token", TOKEN, "--personas", "20", "--historia", "16", "--semilla", "99",
                    "--respuesta-perdida", "0.1", "--salida", str(salida)], check=True)
    envios = [json.loads(x) for x in salida.read_text().splitlines()]
    assert all(e["codigo"] == 200 for e in envios)
    ids = {e["payload"]["participante_id"] for e in envios}
    unicos = {(e["payload"]["participante_id"], e["payload"]["fecha"]) for e in envios}
    assert len(envios) > len(unicos), "el simulador debería haber reenviado algún día"
    for pid in list(ids)[:5]:
        esperado = sum(1 for p, _ in unicos if p == pid)
        assert participante(pid)["dias"] == esperado
    despues = api("/api/resumen")
    assert json.dumps(despues) != json.dumps(antes)


def test_pipeline_con_lo_que_quedo_en_la_base():
    """Lo guardado se puede leer como tabla diaria y el pipeline arma perfiles."""
    psycopg = pytest.importorskip("psycopg")
    sys.path.insert(0, str(RAIZ / "ml"))
    import pipeline
    subprocess.run([sys.executable, str(RAIZ / "integracion/simulador/simulador.py"), "--url", INGEST,
                    "--token", TOKEN, "--personas", "120", "--historia", "21", "--semilla", "7",
                    "--con-arquetipo"], check=True, stdout=subprocess.DEVNULL)
    url = DB.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as c:
        filas = [dict(participante_id=pid, fecha=f.isoformat(), **(d if isinstance(d, dict) else json.loads(d)))
                 for pid, f, d in c.execute("select participante_id, fecha, datos from dias")]
    diario = pd.DataFrame(filas)
    diario = diario[diario.get("arquetipo").notna()] if "arquetipo" in diario else diario
    feats, _ = pipeline.features_por_persona(diario)
    assert len(feats) >= 100


def test_corrida_de_perfiles_desde_el_dashboard():
    """El botón de nueva corrida termina en 'lista' con lo que hay en la base (va al final:
    para entonces ya hay días de otras pruebas, incluido un campo nuevo de otra versión)."""
    import time
    auth = ("admin", ADMIN) if ADMIN else None
    r = requests.post(BACKEND + "/api/corridas", json={}, auth=auth, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    for _ in range(120):
        c = api(f"/api/corridas/{cid}")
        if c["estado"] != "corriendo":
            break
        time.sleep(1)
    assert c["estado"] == "lista", c.get("error")
