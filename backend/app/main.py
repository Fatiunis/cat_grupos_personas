"""API y dashboard de perfiles de uso.

Variables de entorno:
    DATABASE_URL    PostgreSQL en producción; vacío = SQLite local (perfiles.db)
    INGEST_TOKEN    token que la APK envía como "Authorization: Bearer ..." (vacío = sin token)
    ADMIN_USER / ADMIN_PASSWORD   acceso al dashboard (vacío = abierto, solo para uso local)
"""
import csv
import io
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .analisis import cargar_diario, ejecutar_corrida
from synthetic import CALIBRACIONES
from .db import Base, SessionLocal, engine, get_db
from .models import Asignacion, Corrida, Dia, Participante, Retirado, ahora

Base.metadata.create_all(engine)

# Una corrida en segundo plano muere si el servidor se reinicia (Render lo hace al desplegar o tras
# estar inactivo); al arrancar se marcan como interrumpidas para que no queden "corriendo" para siempre.
with SessionLocal() as _db:
    for _c in _db.scalars(select(Corrida).where(Corrida.estado == "corriendo")):
        _c.estado, _c.error = "error", "Se interrumpió porque el servidor se reinició. Vuelve a correrla."
    _db.commit()
app = FastAPI(title="Perfiles de uso")
STATIC = Path(__file__).resolve().parents[1] / "static"
basic = HTTPBasic(auto_error=False)
# Un participante cuenta como activo si envió algo en los últimos días
DIAS_ACTIVO = 3


def admin(cred: HTTPBasicCredentials | None = Depends(basic)):
    clave = os.environ.get("ADMIN_PASSWORD", "")
    if not clave:
        return
    usuario = os.environ.get("ADMIN_USER", "admin")
    if cred is None or not (secrets.compare_digest(cred.username, usuario) and secrets.compare_digest(cred.password, clave)):
        raise HTTPException(401, "Credenciales inválidas", headers={"WWW-Authenticate": "Basic"})


# ---------- Ingesta desde la APK ----------

def token_apk(authorization: str = Header("")):
    token = os.environ.get("INGEST_TOKEN", "")
    if token and not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Token inválido")


def _borrar(db, pid):
    db.execute(delete(Asignacion).where(Asignacion.participante_id == pid))
    db.execute(delete(Dia).where(Dia.participante_id == pid))
    db.execute(delete(Participante).where(Participante.id == pid))
    db.merge(Retirado(id=pid))
    db.commit()


@app.post("/ingest", dependencies=[Depends(token_apk)])
def ingest(cuerpo: dict | list[dict], db: Session = Depends(get_db)):
    dias = cuerpo if isinstance(cuerpo, list) else [cuerpo]
    for d in dias:
        pid, fecha = d.get("participante_id"), d.get("fecha")
        if not isinstance(pid, str) or not 1 <= len(pid) <= 64:
            raise HTTPException(422, "participante_id debe ser texto de 1 a 64 caracteres")
        try:
            fecha = date.fromisoformat(fecha)
        except (TypeError, ValueError):
            raise HTTPException(422, f"Fecha inválida: {fecha!r}")
        if db.get(Retirado, pid):
            # Un envío que estaba en curso cuando la persona se retiró no la vuelve a crear
            raise HTTPException(410, "Participante retirado")
        p = db.get(Participante, pid) or Participante(id=pid)
        p.ultimo_envio = ahora()
        db.add(p)
        datos = {k: v for k, v in d.items() if k not in ("participante_id", "fecha")}
        existente = db.scalar(select(Dia).where(Dia.participante_id == pid, Dia.fecha == fecha))
        if existente:  # un reenvío reemplaza el día
            existente.datos, existente.recibido = datos, ahora()
        else:
            db.add(Dia(participante_id=pid, fecha=fecha, datos=datos))
        db.flush()
    db.commit()
    return {"guardados": len(dias)}


@app.delete("/participantes/{pid}", status_code=204, dependencies=[Depends(token_apk)])
def retiro_desde_apk(pid: str, db: Session = Depends(get_db)):
    """La APK lo llama cuando la persona se retira; reintenta hasta recibir 2xx o 404."""
    db.get(Participante, pid) or _404()
    _borrar(db, pid)


# ---------- API del dashboard ----------

api = Depends(admin)


def _es_simulacion(c):
    return bool((c.resultado or {}).get("simulacion"))


def _calibracion(c):
    sim = (c.resultado or {}).get("simulacion")
    return (sim.get("calibracion") or "base") if sim else None


def _corrida_actual(db):
    """Última corrida terminada con datos reales; las simulaciones no cuentan."""
    for c in db.scalars(select(Corrida).where(Corrida.estado == "lista").order_by(Corrida.id.desc())):
        if not _es_simulacion(c):
            return c
    return None


@app.get("/api/resumen", dependencies=[api])
def resumen(db: Session = Depends(get_db)):
    diario = cargar_diario(db, incluir_excluidos=True)
    hoy = date.today()
    n_part = db.scalar(select(func.count()).select_from(Participante))
    limite = ahora() - timedelta(days=DIAS_ACTIVO)
    activos = db.scalar(select(func.count()).select_from(Participante).where(Participante.ultimo_envio >= limite))
    out = dict(participantes=n_part, activos=activos, excluidos=db.scalar(
        select(func.count()).select_from(Participante).where(Participante.excluido.is_(True))),
        dias=len(diario), con_bfi=db.scalar(select(func.count()).select_from(Participante).where(
            Participante.bfi2_responsabilidad.is_not(None))), serie=[], dias_activo=DIAS_ACTIVO)
    if diario.empty:
        return out
    diario["fecha"] = pd.to_datetime(diario.fecha)
    g = diario.groupby("fecha")
    serie = pd.DataFrame({"personas": g.participante_id.nunique(), "pantalla_mediana": g.pantalla_min.median()})
    if "q_cumplimiento" in diario:
        serie["respuesta_diaria"] = g.q_cumplimiento.apply(lambda s: s.notna().mean())
    serie = serie.reindex(pd.date_range(serie.index.min(), serie.index.max()), fill_value=0)
    out["serie"] = [dict(fecha=f.date().isoformat(), **{k: (None if pd.isna(v) else round(float(v), 3)) for k, v in fila.items()})
                    for f, fila in serie.iterrows()]
    dias_por_persona = diario.groupby("participante_id").size()
    out["con_dias_suficientes"] = int((dias_por_persona >= 14).sum())
    out["fecha_inicio"], out["fecha_fin"] = serie.index.min().date().isoformat(), serie.index.max().date().isoformat()
    out["hoy"] = hoy.isoformat()
    c = _corrida_actual(db)
    out["corrida_actual"] = None if c is None else dict(id=c.id, creada=c.creada.isoformat(), k=c.k)
    return out


@app.get("/api/participantes", dependencies=[api])
def participantes(db: Session = Depends(get_db)):
    c = _corrida_actual(db)
    asign = {a.participante_id: a for a in db.scalars(select(Asignacion).where(Asignacion.corrida_id == c.id))} if c else {}
    nombres = {p["perfil"]: p["nombre"] for p in c.resultado["perfiles"]} if c else {}
    extra = (c.resultado or {}).get("extra", {}) if c else {}
    stats = {pid: (n, f0, f1) for pid, n, f0, f1 in db.execute(
        select(Dia.participante_id, func.count(), func.min(Dia.fecha), func.max(Dia.fecha)).group_by(Dia.participante_id))}
    out = []
    for p in db.scalars(select(Participante).order_by(Participante.id)):
        n, f0, f1 = stats.get(p.id, (0, None, None))
        cobertura = n / ((f1 - f0).days + 1) if f0 else 0
        a = asign.get(p.id)
        out.append(dict(id=p.id, dias=n, primer_dia=f0 and f0.isoformat(), ultimo_dia=f1 and f1.isoformat(),
                        cobertura=round(cobertura, 3), ultimo_envio=p.ultimo_envio and p.ultimo_envio.isoformat(),
                        excluido=p.excluido, notas=p.notas, bfi2=p.bfi2_responsabilidad,
                        perfil=a and a.perfil, perfil_nombre=a and nombres.get(a.perfil), prob=a and round(a.prob, 3),
                        **(extra.get(p.id, {}) if a else {}),
                        perfil2_nombre=a and nombres.get(extra.get(p.id, {}).get("perfil2"))))
    return out


@app.get("/api/participantes/{pid}", dependencies=[api])
def participante(pid: str, db: Session = Depends(get_db)):
    p = db.get(Participante, pid) or _404()
    dias = [dict(fecha=d.fecha.isoformat(), **d.datos) for d in db.scalars(
        select(Dia).where(Dia.participante_id == pid).order_by(Dia.fecha))]
    historial = [dict(corrida=c.id, creada=c.creada.isoformat(), perfil=a.perfil, prob=round(a.prob, 3),
                      nombre=next((x["nombre"] for x in c.resultado["perfiles"] if x["perfil"] == a.perfil), ""))
                 for a, c in db.execute(select(Asignacion, Corrida).join(Corrida).where(
                     Asignacion.participante_id == pid).order_by(Corrida.id.desc()))]
    return dict(id=p.id, excluido=p.excluido, notas=p.notas, bfi2=p.bfi2_responsabilidad, dias=dias, historial=historial)


class CambioParticipante(BaseModel):
    excluido: bool | None = None
    notas: str | None = None
    bfi2: float | None = None


@app.patch("/api/participantes/{pid}", dependencies=[api])
def editar_participante(pid: str, cambio: CambioParticipante, db: Session = Depends(get_db)):
    p = db.get(Participante, pid) or _404()
    if cambio.excluido is not None:
        p.excluido = cambio.excluido
    if cambio.notas is not None:
        p.notas = cambio.notas
    if "bfi2" in cambio.model_fields_set:
        p.bfi2_responsabilidad = cambio.bfi2
    db.commit()
    return {"ok": True}


@app.delete("/api/participantes/{pid}", dependencies=[api])
def borrar_participante(pid: str, db: Session = Depends(get_db)):
    """Retiro del estudio: borra todos los datos de la persona."""
    db.get(Participante, pid) or _404()
    _borrar(db, pid)
    return {"borrado": pid}


@app.post("/api/etiquetas", dependencies=[api])
async def subir_etiquetas(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV con columnas participante_id y bfi2_responsabilidad (resultado del cuestionario)."""
    texto = (await archivo.read()).decode("utf-8-sig")
    filas = list(csv.DictReader(io.StringIO(texto)))
    if not filas or not {"participante_id", "bfi2_responsabilidad"} <= set(filas[0]):
        raise HTTPException(422, "El CSV necesita las columnas participante_id y bfi2_responsabilidad")
    actualizados, desconocidos = 0, []
    for f in filas:
        p = db.get(Participante, f["participante_id"].strip())
        if p is None:
            desconocidos.append(f["participante_id"])
            continue
        valor = f["bfi2_responsabilidad"].strip()
        p.bfi2_responsabilidad = float(valor.replace(",", ".")) if valor else None
        actualizados += 1
    db.commit()
    return dict(actualizados=actualizados, desconocidos=desconocidos[:20], n_desconocidos=len(desconocidos))


@app.get("/api/corridas", dependencies=[api])
def corridas(db: Session = Depends(get_db)):
    return [dict(id=c.id, creada=c.creada.isoformat(), estado=c.estado, k=c.k, k_pedido=c.k_pedido, error=c.error,
                 personas=(c.resultado or {}).get("metricas", {}).get("personas"), simulacion=_es_simulacion(c),
                 calibracion=_calibracion(c))
            for c in db.scalars(select(Corrida).order_by(Corrida.id.desc()))]


class NuevaCorrida(BaseModel):
    k: int | None = None
    simulacion: bool = False  # demostración con personas sintéticas, aparte de los datos reales
    personas: int = 300
    calibracion: str = "base"  # "base" o "estudios" (ajustada a cifras publicadas)


@app.post("/api/corridas", dependencies=[api])
def nueva_corrida(pedido: NuevaCorrida, tareas: BackgroundTasks, db: Session = Depends(get_db)):
    if pedido.k is not None and not 2 <= pedido.k <= 8:
        raise HTTPException(422, "k debe estar entre 2 y 8")
    if pedido.simulacion and not 60 <= pedido.personas <= 1000:
        raise HTTPException(422, "personas debe estar entre 60 y 1000")
    if pedido.calibracion not in CALIBRACIONES:
        raise HTTPException(422, f"calibracion debe ser una de {', '.join(CALIBRACIONES)}")
    sim = dict(personas=pedido.personas, dias=42, semilla=7, calibracion=pedido.calibracion) if pedido.simulacion else None
    c = Corrida(k_pedido=pedido.k, resultado={"simulacion": sim} if sim else {})
    db.add(c)
    db.commit()
    tareas.add_task(ejecutar_corrida, c.id, SessionLocal)
    return dict(id=c.id, estado=c.estado)


@app.get("/api/corridas/{cid}", dependencies=[api])
def corrida(cid: int, db: Session = Depends(get_db)):
    c = db.get(Corrida, cid) or _404()
    res = dict(c.resultado or {})
    puntos = res.pop("puntos_sim", None)
    sim = res.pop("simulacion", None)
    extra = res.pop("extra", {})
    if puntos is None:
        puntos = [dict(id=a.participante_id, perfil=a.perfil, prob=round(a.prob, 3), x=round(a.x, 3), y=round(a.y, 3),
                       **extra.get(a.participante_id, {}))
                  for a in db.scalars(select(Asignacion).where(Asignacion.corrida_id == cid))]
    return dict(id=c.id, creada=c.creada.isoformat(), estado=c.estado, k=c.k, k_pedido=c.k_pedido, error=c.error,
                **res, simulacion=bool(sim), calibracion=_calibracion(c), puntos=puntos)


@app.get("/api/modelo", dependencies=[api])
def modelo(db: Session = Depends(get_db)):
    """Compara la última corrida lista de cada tipo: simulación base, simulación calibrada con
    estudios y datos reales. El modelo final es la calibrada con estudios, con los reales ubicados."""
    ultimas = {}
    for c in db.scalars(select(Corrida).where(Corrida.estado == "lista").order_by(Corrida.id.desc())):
        ultimas.setdefault(_calibracion(c) or "reales", c)
    etapas = []
    for tipo in ("base", "estudios", "reales"):
        c = ultimas.get(tipo)
        if c is None:
            etapas.append(dict(tipo=tipo, id=None))
            continue
        res = c.resultado or {}
        nombres = {p["perfil"]: p["nombre"] for p in res.get("perfiles", [])}
        if tipo == "reales":
            ubic = [dict(id=a.participante_id, perfil=a.perfil, nombre=nombres.get(a.perfil), prob=round(a.prob, 3))
                    for a in db.scalars(select(Asignacion).where(Asignacion.corrida_id == c.id))]
        else:
            ubic = [dict(id=u["id"], perfil=u["perfil"], nombre=nombres.get(u["perfil"]), prob=u["prob"],
                         atipico=u.get("atipico"), dias=u.get("dias")) for u in res.get("ubicados", [])]
        etapas.append(dict(tipo=tipo, id=c.id, creada=c.creada.isoformat(), k=c.k, metricas=res.get("metricas", {}),
                           perfiles=[dict(perfil=p["perfil"], nombre=p["nombre"], n=p["n"]) for p in res.get("perfiles", [])],
                           niveles={k: v for k, v in (res.get("niveles") or {}).items() if k in ("cortes", "rmse", "con_bfi", "faltan")},
                           ubicados=ubic))
    return dict(etapas=etapas, final="estudios")


class CambioPerfil(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None


@app.patch("/api/corridas/{cid}/perfiles/{perfil}", dependencies=[api])
def renombrar_perfil(cid: int, perfil: int, cambio: CambioPerfil, db: Session = Depends(get_db)):
    c = db.get(Corrida, cid) or _404()
    res = dict(c.resultado)
    res["perfiles"] = [dict(p, **cambio.model_dump(exclude_none=True)) if p["perfil"] == perfil else p for p in res["perfiles"]]
    c.resultado = res  # reasignar para que SQLAlchemy detecte el cambio en el JSON
    db.commit()
    return {"ok": True}


@app.delete("/api/corridas/{cid}", dependencies=[api])
def borrar_corrida(cid: int, db: Session = Depends(get_db)):
    db.get(Corrida, cid) or _404()
    db.execute(delete(Asignacion).where(Asignacion.corrida_id == cid))
    db.execute(delete(Corrida).where(Corrida.id == cid))
    db.commit()
    return {"borrada": cid}


# ---------- Exportación ----------

def _csv(df, nombre):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.get("/api/exportar/dias.csv", dependencies=[api])
def exportar_dias(db: Session = Depends(get_db)):
    return _csv(cargar_diario(db, incluir_excluidos=True), "dias.csv")


@app.get("/api/exportar/perfiles.csv", dependencies=[api])
def exportar_perfiles(corrida: int | None = None, db: Session = Depends(get_db)):
    c = db.get(Corrida, corrida) if corrida else _corrida_actual(db)
    if c is None:
        _404()
    nombres = {p["perfil"]: p["nombre"] for p in c.resultado["perfiles"]}
    if _es_simulacion(c):
        filas = [dict(participante_id=p["id"], perfil=p["perfil"], nombre_perfil=nombres.get(p["perfil"]), prob=p["prob"])
                 for p in c.resultado.get("puntos_sim", [])]
    else:
        filas = [dict(participante_id=a.participante_id, perfil=a.perfil, nombre_perfil=nombres.get(a.perfil), prob=a.prob)
                 for a in db.scalars(select(Asignacion).where(Asignacion.corrida_id == c.id))]
    return _csv(pd.DataFrame(filas), f"perfiles_corrida_{c.id}.csv")


def _404():
    raise HTTPException(404, "No encontrado")


@app.get("/salud")
def salud():
    return {"ok": True, "hora": datetime.now(timezone.utc).isoformat()}


SIN_CACHE = {"Cache-Control": "no-cache"}  # el navegador revisa siempre si hay versión nueva


@app.get("/", dependencies=[api])
def inicio():
    # Cada archivo lleva su fecha de cambio en el enlace (?v=...), así un navegador que guardó
    # la versión anterior baja la nueva tras una actualización en lugar de mezclar versiones.
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for nombre in ("app.js", "estilos.css"):
        version = int((STATIC / nombre).stat().st_mtime)
        html = html.replace(f"/static/{nombre}\"", f"/static/{nombre}?v={version}\"")
    return HTMLResponse(html, headers=SIN_CACHE)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
