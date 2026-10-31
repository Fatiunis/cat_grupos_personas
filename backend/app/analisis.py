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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml"))
from pipeline import DIAS_MINIMOS, describir_perfiles, elegir_k, features_por_persona, quitar_redundantes  # noqa: E402

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


def calcular(diario, etiquetas=None, k=None):
    """Devuelve (resultado, asignaciones). Misma lógica que pipeline.main()."""
    feats, excluidas = features_por_persona(diario)
    if len(feats) < 30:
        raise ValueError(f"Hay {len(feats)} personas con al menos {DIAS_MINIMOS} días; se necesitan 30 o más.")
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
    prob = gm.predict_proba(Z).max(axis=1)

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
                    baja_confianza=float((prob < 0.6).mean()),
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
    if etiquetas is not None:
        y = etiquetas.reindex(feats.index)
        if y.notna().sum() >= 30:
            ok = y.notna()
            etiqueta_por_perfil = [dict(perfil=int(p), media=g.mean(), sd=g.std(), n=int(g.count()))
                                   for p, g in y[ok].groupby(perfiles[ok])]
            pred = cross_val_predict(make_pipeline(RobustScaler(), HistGradientBoostingRegressor(max_depth=3, random_state=0)),
                                     X[ok], y[ok], cv=5)
            metricas["r_responsabilidad"] = float(np.corrcoef(pred, y[ok])[0, 1])

    resultado = _limpio(dict(metricas=metricas, tabla_k=tabla_k.to_dict(orient="records"), perfiles=por_perfil,
                             cruce_arquetipos=cruce, responsabilidad=etiqueta_por_perfil))
    asign = [dict(participante_id=pid, perfil=int(perfiles[pid]), prob=float(pr), x=float(zz[0]), y=float(zz[1] if len(zz) > 1 else 0))
             for pid, pr, zz in zip(feats.index, prob, Z)]
    return resultado, asign


def ejecutar_corrida(corrida_id, session_factory):
    """Pensado para correr en segundo plano: lee los datos, calcula y guarda."""
    with session_factory() as db:
        corrida = db.get(Corrida, corrida_id)
        try:
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
