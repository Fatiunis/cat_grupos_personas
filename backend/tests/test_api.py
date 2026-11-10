"""Pruebas de la API con SQLite temporal. Ejecutar desde backend/: python -m pytest tests"""
import io
import os
import tempfile
import time

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "prueba.db")
os.environ["INGEST_TOKEN"] = "secreto"

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from cargar_sinteticos import main as cargar  # noqa: E402

cliente = TestClient(app)
AUTH = {"Authorization": "Bearer secreto"}


def test_ingest_pide_token_y_es_idempotente():
    dia = {"participante_id": "abc", "fecha": "2026-10-01", "pantalla_min": 100, "q_puntual": "si"}
    assert cliente.post("/ingest", json=dia).status_code == 401
    assert cliente.post("/ingest", json=dia, headers=AUTH).status_code == 200
    assert cliente.post("/ingest", json={**dia, "pantalla_min": 120}, headers=AUTH).status_code == 200
    p = cliente.get("/api/participantes/abc").json()
    assert len(p["dias"]) == 1 and p["dias"][0]["pantalla_min"] == 120
    assert cliente.post("/ingest", json={"fecha": "2026-10-01"}, headers=AUTH).status_code == 422
    assert cliente.post("/ingest", json=[{**dia, "fecha": "2026-10-02"}, {**dia, "fecha": "2026-10-03"}],
                        headers=AUTH).json() == {"guardados": 2}


def test_retiro_desde_la_apk():
    cliente.post("/ingest", json={"participante_id": "retiro", "fecha": "2026-10-01"}, headers=AUTH)
    assert cliente.delete("/participantes/retiro").status_code == 401
    assert cliente.delete("/participantes/retiro", headers=AUTH).status_code == 204
    assert cliente.get("/api/participantes/retiro").status_code == 404
    assert cliente.delete("/participantes/retiro", headers=AUTH).status_code == 404
    # Un día que llega después del retiro no recrea a la persona
    assert cliente.post("/ingest", json={"participante_id": "retiro", "fecha": "2026-10-02"}, headers=AUTH).status_code == 410
    assert cliente.get("/api/participantes/retiro").status_code == 404


def test_ids_invalidos_dan_422():
    for pid in ["x" * 65, 12345, "", None]:
        r = cliente.post("/ingest", json={"participante_id": pid, "fecha": "2026-10-01"}, headers=AUTH)
        assert r.status_code == 422, pid
    assert cliente.post("/ingest", json={"participante_id": "ok", "fecha": 20261001}, headers=AUTH).status_code == 422


def test_flujo_completo_con_sinteticos():
    cargar(personas=120, dias=30, semilla=1, corrida=False, borrar=True)
    r = cliente.get("/api/resumen").json()
    assert r["participantes"] == 120 and r["activos"] == 120 and r["serie"]

    cid = cliente.post("/api/corridas", json={"k": 4}).json()["id"]
    for _ in range(60):
        c = cliente.get(f"/api/corridas/{cid}").json()
        if c["estado"] != "corriendo":
            break
        time.sleep(1)
    assert c["estado"] == "lista", c["error"]
    assert c["k"] == 4 and len(c["puntos"]) == c["metricas"]["personas"]
    assert c["responsabilidad"] and "ari_arquetipos" in c["metricas"]

    assert cliente.patch(f"/api/corridas/{cid}/perfiles/0", json={"nombre": "Prueba"}).status_code == 200
    lista = cliente.get("/api/participantes").json()
    assert any(p["perfil_nombre"] == "Prueba" for p in lista)

    pid = lista[0]["id"]
    csv = f"participante_id,bfi2_responsabilidad\n{pid},4,5\ndesconocido,3\n".replace("4,5", '"4,5"')
    r = cliente.post("/api/etiquetas", files={"archivo": ("e.csv", io.BytesIO(csv.encode()))}).json()
    assert r["actualizados"] == 1 and r["n_desconocidos"] == 1
    assert cliente.get(f"/api/participantes/{pid}").json()["bfi2"] == 4.5

    assert cliente.patch(f"/api/participantes/{pid}", json={"excluido": True}).status_code == 200
    dias = pd.read_csv(io.StringIO(cliente.get("/api/exportar/dias.csv").text))
    assert pid in set(dias.participante_id)
    assert cliente.delete(f"/api/participantes/{pid}").status_code == 200
    assert cliente.get(f"/api/participantes/{pid}").status_code == 404
    assert "perfil" in cliente.get("/api/exportar/perfiles.csv").text


def test_corrida_con_sinteticos_y_reales_mezclados():
    from app.analisis import calcular
    from synthetic import generar
    diario, _ = generar(80, 20, 3)
    diario.loc[diario.participante_id < "p00020", "arquetipo"] = None  # simula datos reales sin arquetipo
    resultado, asign = calcular(diario, None, 3)
    assert "ari_arquetipos" in resultado["metricas"] and len(asign) == resultado["metricas"]["personas"]


def test_simulacion_va_aparte_de_los_datos_reales():
    for f in ["2026-11-01", "2026-11-02", "2026-11-03"]:
        cliente.post("/ingest", json={"participante_id": "abc", "fecha": f, "pantalla_min": 200, "desbloqueos": 60}, headers=AUTH)
    antes = cliente.get("/api/participantes").json()
    resumen = cliente.get("/api/resumen").json()
    assert cliente.post("/api/corridas", json={"simulacion": True, "personas": 10}).status_code == 422
    cid = cliente.post("/api/corridas", json={"simulacion": True, "personas": 120}).json()["id"]
    t = time.time()
    for _ in range(120):
        c = cliente.get(f"/api/corridas/{cid}").json()
        if c["estado"] != "corriendo":
            break
        time.sleep(1)
    print("simulacion seg", round(time.time() - t, 1))
    assert c["estado"] == "lista", c["error"]
    assert c["simulacion"] and len(c["puntos"]) == 120 and c["responsabilidad"]
    assert "puntos_sim" not in c and "ari_arquetipos" in c["metricas"]
    # Los participantes reales con pocos días se ubican en los perfiles de la simulación
    ub = {u["id"]: u for u in c["ubicados"]}
    assert "abc" in ub and ub["abc"]["dias"] == 3 and 0 <= ub["abc"]["perfil"] < c["k"]
    assert not any(i.startswith("p0") for i in ub)
    assert any(x["id"] == cid and x["simulacion"] for x in cliente.get("/api/corridas").json())
    # Nada real cambia: mismos participantes y la corrida "actual" sigue siendo la real
    assert cliente.get("/api/participantes").json() == antes
    assert cliente.get("/api/resumen").json() == resumen
    csv = pd.read_csv(io.StringIO(cliente.get(f"/api/exportar/perfiles.csv?corrida={cid}").text))
    assert len(csv) == 120 and csv.participante_id.str.startswith("p").all()


def test_simulacion_calibrada_con_estudios_y_comparacion_de_modelos():
    assert cliente.post("/api/corridas", json={"simulacion": True, "calibracion": "otra"}).status_code == 422
    cid = cliente.post("/api/corridas", json={"simulacion": True, "personas": 120, "calibracion": "estudios"}).json()["id"]
    for _ in range(120):
        c = cliente.get(f"/api/corridas/{cid}").json()
        if c["estado"] != "corriendo":
            break
        time.sleep(1)
    assert c["estado"] == "lista", c["error"]
    assert c["calibracion"] == "estudios"
    niv = c["niveles"]
    assert niv["criterio"] == "cuartiles" and len(niv["cortes"]) == 3 and len(niv["grupos"]) == 4
    assert sum(g["n"] for g in niv["grupos"]) == niv["con_bfi"]
    m = cliente.get("/api/modelo").json()
    etapas = {e["tipo"]: e for e in m["etapas"]}
    assert m["final"] == "estudios" and etapas["estudios"]["id"] == cid
    assert etapas["estudios"]["k"] == c["k"] and "ari_arquetipos" in etapas["estudios"]["metricas"]


def test_pocos_dias_entre_semana_da_mensaje_claro():
    # Antes fallaba con el error "True" cuando nadie tenía días de fin de semana
    from app.analisis import calcular
    d = pd.DataFrame([dict(participante_id="a", fecha=f"2026-11-0{i}", pantalla_min=100, bateria_min_pct=50,
                           hora_primer_uso=7, hora_ultimo_uso=23) for i in range(2, 7)])
    try:
        calcular(d)
    except ValueError as e:
        assert "se necesitan 30" in str(e)
    else:
        raise AssertionError("debía pedir más personas")


def test_panel_pide_la_version_nueva_de_sus_archivos():
    # Un navegador con la versión anterior guardada mezclaba HTML nuevo con JS viejo y el panel quedaba vacío
    r = cliente.get("/")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert "/static/app.js?v=" in r.text and "/static/estilos.css?v=" in r.text
