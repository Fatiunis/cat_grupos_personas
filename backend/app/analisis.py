"""Corre el pipeline de ml/pipeline.py sobre los datos de la base y guarda el resultado."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from threadpoolctl import threadpool_limits

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml"))
from pipeline import DIAS_MINIMOS, describir_perfiles, elegir_k, features_por_persona, quitar_redundantes  # noqa: E402
from synthetic import generar  # noqa: E402

from .models import Asignacion, Corrida, Dia, Participante  # noqa: E402

# Texto para nombrar perfiles según la variable que más los distingue (alto, bajo)
NOMBRES_VARIABLES = {
    "pantalla_min_med": ("mucha pantalla", "poca pantalla"),
    "desbloqueos_med": ("muchos desbloqueos", "pocos desbloqueos"),
    "uso_nocturno_min_med": ("nocturno", "sin uso nocturno"),
    "pct_social_med": ("redes sociales", "poco social"),
    "pct_juegos_med": ("juegos", "sin juegos"),
    "pct_productividad_med": ("productividad", "poca productividad"),
    "hora_primer_uso_sd": ("horarios irregulares", "horarios regulares"),
    "veces_bateria_baja_med": ("batería al límite", "batería cuidada"),
    "pasos_med": ("activo", "sedentario"),
    "lugares_distintos_med": ("se mueve mucho", "pocos lugares"),
}

CORTOS = {"pantalla_min_med": "pantalla", "desbloqueos_med": "desbloqueos", "uso_nocturno_min_med": "uso nocturno",
          "pct_social_med": "redes", "pct_juegos_med": "juegos", "pct_productividad_med": "productividad",
          "hora_primer_uso_sd": "irregular", "veces_bateria_baja_med": "batería baja", "pasos_med": "pasos",
          "lugares_distintos_med": "lugares"}

# Métricas legibles (en sus unidades) que el dashboard muestra por perfil
METRICAS_LEGIBLES = ["pantalla_min", "desbloqueos", "uso_nocturno_min", "hora_primer_uso",
                     "hora_ultimo_uso", "notificaciones", "q_cumplimiento"]
CATEGORIAS = ["social", "mensajeria", "juegos", "video", "productividad", "educacion"]


def cargar_diario(db: Session, incluir_excluidos=False):
    q = select(Dia.participante_id, Dia.fecha, Dia.datos).join(Participante)
    if not incluir_excluidos:
        q = q.where(Participante.excluido.is_(False))
    filas = [{**datos, "participante_id": pid, "fecha": fecha.isoformat()} for pid, fecha, datos in db.execute(q)]
    return pd.DataFrame(filas)


def medianas_por_persona(diario):
    d = diario.copy()
    cols = [c for c in METRICAS_LEGIBLES if c in d.columns]
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    g = d.groupby("participante_id")
    out = pd.DataFrame(index=g.size().index)
    for c in cols:
        # Las horas llegan continuas desde la medianoche (25.5 = 01:30), así que la mediana sirve tal cual
        out[c] = g[c].median()
    for c in CATEGORIAS:
        if f"{c}_min" in d.columns:
            out[f"pct_{c}"] = (d[f"{c}_min"] / d.pantalla_min.clip(lower=1)).groupby(d.participante_id).median()
    return out


def nombres_automaticos(z):
    """Nombra cada perfil por sus dos rasgos más marcados. Si dos perfiles quedan con el mismo
    nombre, a cada uno se le agrega la variable en la que más se aleja del resto del grupo."""
    z = z[[c for c in z.columns if c in NOMBRES_VARIABLES]]
    base = {}
    for p, fila in z.iterrows():
        top = fila.abs().sort_values(ascending=False).index[:2]
        base[p] = frozenset(NOMBRES_VARIABLES[c][0 if fila[c] > 0 else 1] for c in top)
    nombres = {}
    for p, fila in z.iterrows():
        top = fila.abs().sort_values(ascending=False).index[:2]
        nombre = ", ".join(NOMBRES_VARIABLES[c][0 if fila[c] > 0 else 1] for c in top).capitalize()
        grupo = [q for q in base if base[q] == base[p]]
        if len(grupo) > 1:
            dif = fila - z.loc[grupo].mean()
            v = dif.abs().idxmax()
            nombre += f" ({'más' if dif[v] > 0 else 'menos'} {CORTOS[v]})"
        nombres[p] = nombre or f"Perfil {p}"
    return nombres


def _limpio(x):
    """Convierte NaN e infinitos a None para que el JSON sea válido."""
    if isinstance(x, dict):
        return {k: _limpio(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_limpio(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), 4)
    if isinstance(x, np.integer):
        return int(x)
    return x


# Niveles de responsabilidad según el puntaje BFI-2 (escala 1 a 5)
CORTES_NIVEL = (2.95, 3.95)
NIVELES = ["baja", "media", "alta"]


def nivel_de(v):
    return NIVELES[int(v > CORTES_NIVEL[0]) + int(v > CORTES_NIVEL[1])]


def niveles_responsabilidad(feats, y, perfiles, legibles):
    """Agrupa a las personas con BFI-2 en baja, media y alta, y describe el uso de cada nivel."""
    nivel = y.map(nivel_de)
    claves = [c for c in NOMBRES_VARIABLES if c in feats.columns]
    z = (feats[claves] - feats[claves].mean()) / feats[claves].std()
    out = []
    for nv in NIVELES:
        ids = nivel[nivel == nv].index
        if not len(ids):
            continue
        out.append(dict(nivel=nv, n=int(len(ids)), media_bfi=float(y[ids].mean()),
                        z=z.loc[ids].mean().round(2).to_dict(), medianas=legibles.loc[ids].median().to_dict(),
                        perfiles={int(p): int(c) for p, c in perfiles[ids].value_counts().items()}))
    return dict(cortes=list(CORTES_NIVEL), con_bfi=int(len(y)), grupos=out)


def calcular(diario, etiquetas=None, k=None, ubicar=None):
    """Devuelve (resultado, asignaciones). Misma lógica que pipeline.main().

    ubicar: días de otras personas (los participantes reales en una simulación). No entran al
    ajuste del modelo; solo se ubican después en los perfiles encontrados, aunque tengan pocos días.
    """
    feats, excluidas = features_por_persona(diario)
    if len(feats) < 30:
        raise ValueError(f"Hay {len(feats)} personas con al menos {DIAS_MINIMOS} días; se necesitan 30 o más.")
    nuevos = None
    if ubicar is not None and not ubicar.empty:
        # Mismas transformaciones que el grupo del modelo, sin que estas personas cambien el ajuste
        nuevos, _ = features_por_persona(ubicar, dias_minimos=1, ajuste=feats.attrs["ajuste"])
        # Llevar pocos días no es un rasgo de uso: se les pone la duración típica para no alejarlos por eso
        nuevos["dias_validos"] = feats.dias_validos.median()
    X = quitar_redundantes(feats)
    escalador = RobustScaler().fit(X)
    pca = PCA(n_components=0.9, random_state=0).fit(escalador.transform(X))
    Z = pca.transform(escalador.transform(X))

    ks = range(3, max(4, min(9, len(feats) // 10 + 1)))
    tabla_k = elegir_k(Z, ks=ks)
    k_auto = tabla_k[tabla_k.estabilidad > 0.85].sort_values("bic").k
    k_auto = int(k_auto.iloc[0]) if len(k_auto) else int(tabla_k.sort_values("bic").k.iloc[0])
    k_final = k or k_auto
    gm = GaussianMixture(k_final, covariance_type="tied", n_init=5, random_state=0).fit(Z)
    perfiles = pd.Series(gm.predict(Z), index=feats.index, name="perfil")
    P = gm.predict_proba(Z)
    prob = P.max(axis=1)
    # Atípico: tan lejos de todos los perfiles como el 2,5 % más alejado del grupo con que se ajustó.
    # La probabilidad solo compara perfiles entre sí; esta marca mira la distancia a todos.
    umbral_atipico = float(np.percentile(gm.score_samples(Z), 2.5))

    def detalle(probs, Zs):
        orden = np.argsort(-probs, axis=1)
        atip = gm.score_samples(Zs) < umbral_atipico
        return [dict(perfil2=int(o[1]) if len(o) > 1 else None, prob2=round(float(pr[o[1]]), 3) if len(o) > 1 else 0.0,
                     atipico=bool(a)) for pr, o, a in zip(probs, orden, atip)]

    z = describir_perfiles(feats, perfiles)
    legibles = medianas_por_persona(diario).reindex(feats.index)
    nombres = nombres_automaticos(z)
    por_perfil = []
    for p in sorted(perfiles.unique()):
        miembros = perfiles[perfiles == p].index
        por_perfil.append(dict(
            perfil=int(p), nombre=nombres[p], descripcion="",
            n=int(len(miembros)), prob_media=float(prob[perfiles == p].mean()),
            z=z.loc[p].to_dict(), medianas=legibles.loc[miembros].median().to_dict(),
        ))

    metricas = dict(personas=len(feats), sin_perfil_pocos_dias=len(excluidas), features=feats.shape[1],
                    features_sin_redundantes=X.shape[1], componentes_pca=Z.shape[1], k_automatico=k_auto,
                    baja_confianza=float((prob < 0.6).mean()), atipicos=int((gm.score_samples(Z) < umbral_atipico).sum()),
                    varianza_mapa=float(pca.explained_variance_ratio_[:2].sum()))

    if len(perfiles.unique()) > 1 and perfiles.value_counts().min() >= 2:
        Xtr, Xte, ytr, yte = train_test_split(X, perfiles, test_size=0.25, stratify=perfiles, random_state=0)
        metricas["exactitud_clasificador"] = float(HistGradientBoostingClassifier(random_state=0).fit(Xtr, ytr).score(Xte, yte))

    cruce = None
    # Solo los datos sintéticos traen arquetipo; si se mezclan con reales se compara sobre los sintéticos
    verdad = diario.groupby("participante_id").arquetipo.first().reindex(feats.index).dropna() \
        if "arquetipo" in diario.columns else pd.Series(dtype=object)
    if len(verdad) >= 2:
        metricas["ari_arquetipos"] = float(adjusted_rand_score(verdad, perfiles[verdad.index]))
        ct = pd.crosstab(verdad, perfiles[verdad.index])
        cruce = dict(filas=ct.index.tolist(), columnas=[int(c) for c in ct.columns], valores=ct.values.tolist())

    etiqueta_por_perfil = None
    modelo_resp = None
    n_etiquetas = 0
    if etiquetas is not None:
        y = etiquetas.reindex(feats.index)
        n_etiquetas = int(y.notna().sum())
        if n_etiquetas >= 30:
            ok = y.notna()
            etiqueta_por_perfil = [dict(perfil=int(p), media=g.mean(), sd=g.std(), n=int(g.count()))
                                   for p, g in y[ok].groupby(perfiles[ok])]
            regresor = lambda: make_pipeline(RobustScaler(), HistGradientBoostingRegressor(max_depth=3, random_state=0))  # noqa: E731
            pred = cross_val_predict(regresor(), X[ok], y[ok], cv=5)
            metricas["r_responsabilidad"] = float(np.corrcoef(pred, y[ok])[0, 1])
            modelo_resp = (regresor().fit(X[ok], y[ok]), float(np.sqrt(np.mean((pred - y[ok]) ** 2))), y, ok)

    niveles = None
    if modelo_resp is not None:
        modelo, rmse, y, ok = modelo_resp
        niveles = niveles_responsabilidad(feats, y[ok], perfiles[ok], legibles)
        niveles["rmse"] = rmse
        estimar = [(pid, fila) for pid, fila in X[~ok].iterrows()]
        if nuevos is not None and len(nuevos):
            estimar += list(nuevos[X.columns].iterrows())
        if estimar:
            valores = modelo.predict(pd.DataFrame([f for _, f in estimar], columns=X.columns))
            niveles["estimados"] = [dict(id=pid, valor=float(v), nivel=nivel_de(v)) for (pid, _), v in zip(estimar, valores)]
    else:
        niveles = dict(faltan=max(0, 30 - n_etiquetas), con_bfi=n_etiquetas)

    resultado = _limpio(dict(metricas=metricas, tabla_k=tabla_k.to_dict(orient="records"), perfiles=por_perfil,
                             cruce_arquetipos=cruce, responsabilidad=etiqueta_por_perfil, niveles=niveles))
    resultado["extra"] = {pid: d for pid, d in zip(feats.index, detalle(P, Z))}
    if nuevos is not None and len(nuevos):
        Zn = pca.transform(escalador.transform(nuevos[X.columns]))
        pn = gm.predict_proba(Zn)
        dias_n = ubicar.groupby("participante_id").size()
        resultado["ubicados"] = [dict(id=pid, perfil=int(pr.argmax()), prob=round(float(pr.max()), 3), dias=int(dias_n.get(pid, 0)),
                                      x=round(float(zz[0]), 3), y=round(float(zz[1] if len(zz) > 1 else 0), 3), **d)
                                 for pid, pr, zz, d in zip(nuevos.index, pn, Zn, detalle(pn, Zn))]
    asign = [dict(participante_id=pid, perfil=int(perfiles[pid]), prob=float(pr), x=float(zz[0]), y=float(zz[1] if len(zz) > 1 else 0))
             for pid, pr, zz in zip(feats.index, prob, Z)]
    return resultado, asign


def _corrida_simulada(db, corrida, sim):
    """Demostración: genera personas sintéticas en memoria y corre el mismo análisis.

    No toca las tablas de participantes, días ni asignaciones: los puntos del mapa quedan
    dentro del resultado, así una simulación nunca se mezcla con los datos reales. Los
    participantes reales que ya mandaron días se ubican en los perfiles de la simulación.
    """
    diario, etiq = generar(sim["personas"], sim.get("dias", 42), sim.get("semilla", 7))
    diario["fecha"] = diario.fecha.astype(str)
    bfi = etiq.set_index("participante_id").bfi2_responsabilidad
    reales = cargar_diario(db)
    if not reales.empty and "pantalla_min" in reales.columns:
        reales = reales[~reales.participante_id.isin(set(diario.participante_id))]
        # Columnas que la app aún no manda quedan vacías y se rellenan con la mediana del modelo
        reales = reales.reindex(columns=reales.columns.union(diario.columns.drop("arquetipo", errors="ignore")))
        for c in reales.columns.difference(["participante_id", "fecha"]):
            if reales[c].dtype == object:
                reales[c] = pd.to_numeric(reales[c], errors="coerce") if c != "arquetipo" else reales[c]
    else:
        reales = None
    resultado, asign = calcular(diario, bfi, corrida.k_pedido, ubicar=reales)
    resultado["simulacion"] = sim
    extra = resultado.pop("extra")
    resultado["puntos_sim"] = [dict(id=a["participante_id"], perfil=a["perfil"], prob=round(a["prob"], 3),
                                    x=round(a["x"], 3), y=round(a["y"], 3), **extra[a["participante_id"]]) for a in asign]
    corrida.resultado, corrida.k, corrida.estado = resultado, len(resultado["perfiles"]), "lista"


def ejecutar_corrida(corrida_id, session_factory):
    """Pensado para correr en segundo plano: lee los datos, calcula y guarda."""
    # Con un solo hilo el cálculo es varias veces más rápido en servidores con poca CPU
    with threadpool_limits(1), session_factory() as db:
        corrida = db.get(Corrida, corrida_id)
        sim = (corrida.resultado or {}).get("simulacion")
        try:
            if sim:
                _corrida_simulada(db, corrida, sim)
                db.commit()
                return
            diario = cargar_diario(db)
            if diario.empty:
                raise ValueError("No hay datos diarios cargados.")
            etiq = pd.Series(dict(db.execute(select(Participante.id, Participante.bfi2_responsabilidad).where(
                Participante.bfi2_responsabilidad.is_not(None))).all()), dtype=float)
            resultado, asign = calcular(diario, etiq if len(etiq) else None, corrida.k_pedido)
            db.execute(delete(Asignacion).where(Asignacion.corrida_id == corrida_id))
            db.add_all(Asignacion(corrida_id=corrida_id, **a) for a in asign)
            corrida.resultado, corrida.k, corrida.estado = resultado, len(resultado["perfiles"]), "lista"
        except Exception as e:  # el error se muestra en el dashboard
            corrida.estado, corrida.error = "error", str(e)
        db.commit()
