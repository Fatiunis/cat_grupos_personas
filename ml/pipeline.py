"""Pipeline de perfiles: features por persona, clustering, asignación y validación.

Uso:
    python pipeline.py --datos datos_sinteticos.csv --etiquetas etiquetas_sinteticas.csv
"""
import argparse

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

DIAS_MINIMOS = 14
# Horas que cruzan medianoche se miden desde el mediodía para que 23 h y 1 h queden cerca.
HORAS_NOCHE = ["hora_ultimo_uso", "hora_inicio_sueno"]
EXCLUIR = {"participante_id", "fecha", "arquetipo"}


def limpiar(diario):
    d = diario.copy()
    d = d[(d.pantalla_min >= 0) & (d.pantalla_min <= 24 * 60)]
    d = d[d.bateria_min_pct.between(0, 100)]
    for c in HORAS_NOCHE:
        d[c] = np.mod(d[c] - 12, 24)
    cats = [c for c in d.columns if c.endswith("_min") and c not in ("pantalla_min", "uso_nocturno_min", "sesion_media_min")]
    for c in cats:
        d[f"pct_{c[:-4]}"] = d[c] / d.pantalla_min.clip(lower=1)
    p = d[[f"pct_{c[:-4]}" for c in cats]].clip(1e-6, 1)
    d["entropia_categorias"] = -(p * np.log(p)).sum(axis=1)
    d["finde"] = pd.to_datetime(d.fecha).dt.dayofweek >= 5
    return d


def features_por_persona(diario):
    d = limpiar(diario)
    dias = d.groupby("participante_id").size()
    validos = dias[dias >= DIAS_MINIMOS].index
    d = d[d.participante_id.isin(validos)]
    num = [c for c in d.select_dtypes("number").columns if c not in EXCLUIR]
    g = d.groupby("participante_id")[num]
    feats = pd.concat([g.median().add_suffix("_med"), g.std().add_suffix("_sd")], axis=1)
    # Diferencia semana vs fin de semana en las variables de horario
    for c in ["hora_primer_uso", "hora_ultimo_uso", "pantalla_min"]:
        s = d.groupby(["participante_id", "finde"])[c].median().unstack()
        feats[f"{c}_dif_finde"] = (s[True] - s[False]).reindex(feats.index)
    feats["dias_validos"] = dias.reindex(feats.index)
    # Logaritmo para tiempos y conteos sesgados
    for c in feats.columns:
        if (feats[c] >= 0).all() and feats[c].skew() > 1:
            feats[c] = np.log1p(feats[c])
    feats = feats.fillna(feats.median())
    excluidas = sorted(set(dias.index) - set(validos))
    return feats, excluidas


def quitar_redundantes(X, umbral=0.9):
    corr = X.corr().abs()
    sup = corr.where(np.triu(np.ones(corr.shape, dtype=bool), 1))
    return X.drop(columns=[c for c in sup.columns if (sup[c] > umbral).any()])


def elegir_k(Z, ks=range(3, 9), semilla=0):
    res = []
    for k in ks:
        gm = GaussianMixture(k, covariance_type="tied", n_init=3, random_state=semilla).fit(Z)
        lab = gm.predict(Z)
        res.append(dict(k=k, bic=gm.bic(Z), silueta=silhouette_score(Z, lab), estabilidad=estabilidad(Z, k)))
    return pd.DataFrame(res)


def estabilidad(Z, k, repeticiones=5, frac=0.8, semilla=0):
    """ARI medio entre clusterings hechos sobre submuestras distintas."""
    rng = np.random.default_rng(semilla)
    ref = GaussianMixture(k, covariance_type="tied", n_init=3, random_state=semilla).fit(Z)
    aris = []
    for r in range(repeticiones):
        idx = rng.choice(len(Z), int(frac * len(Z)), replace=False)
        gm = GaussianMixture(k, covariance_type="tied", n_init=3, random_state=r + 1).fit(Z[idx])
        aris.append(adjusted_rand_score(ref.predict(Z), gm.predict(Z)))
    return float(np.mean(aris))


def describir_perfiles(feats, perfiles):
    claves = ["pantalla_min_med", "desbloqueos_med", "uso_nocturno_min_med", "pct_social_med",
              "pct_juegos_med", "pct_productividad_med", "hora_primer_uso_sd", "veces_bateria_baja_med",
              "pasos_med", "lugares_distintos_med"]
    claves = [c for c in claves if c in feats.columns]
    z = (feats[claves] - feats[claves].mean()) / feats[claves].std()
    return z.groupby(perfiles).mean().round(2)


def main(ruta_datos, ruta_etiquetas=None, k=None):
    diario = pd.read_csv(ruta_datos)
    feats, excluidas = features_por_persona(diario)
    print(f"Personas con perfil: {len(feats)}; sin perfil por pocos días: {len(excluidas)}")

    X = quitar_redundantes(feats)
    escalador = RobustScaler().fit(X)
    pca = PCA(n_components=0.9, random_state=0).fit(escalador.transform(X))
    Z = pca.transform(escalador.transform(X))
    print(f"Features: {feats.shape[1]} -> {X.shape[1]} sin redundantes -> {Z.shape[1]} componentes PCA")

    tabla_k = elegir_k(Z)
    print("\nSelección del número de perfiles:\n", tabla_k.round(3).to_string(index=False))
    if k is None:
        # Menor BIC entre los k estables; con datos reales revisar la tabla y fijar --k a mano
        k = int(tabla_k[tabla_k.estabilidad > 0.85].sort_values("bic").k.iloc[0])
    gm = GaussianMixture(k, covariance_type="tied", n_init=5, random_state=0).fit(Z)
    perfiles = pd.Series(gm.predict(Z), index=feats.index, name="perfil")
    prob = gm.predict_proba(Z).max(axis=1)
    print(f"\nk elegido = {k}; personas con baja confianza (<0,6): {(prob < 0.6).mean():.1%}")
    print("\nPerfiles (z-score medio de variables clave):\n", describir_perfiles(feats, perfiles).to_string())

    if "arquetipo" in diario.columns:
        verdad = diario.groupby("participante_id").arquetipo.first().reindex(feats.index)
        print(f"\nARI contra arquetipos plantados: {adjusted_rand_score(verdad, perfiles):.3f} (meta >= 0,7)")
        print(pd.crosstab(verdad, perfiles).to_string())

    # Clasificador que asigna perfil a personas nuevas sin rehacer el clustering
    Xtr, Xte, ytr, yte = train_test_split(X, perfiles, test_size=0.25, stratify=perfiles, random_state=0)
    clf = HistGradientBoostingClassifier(random_state=0).fit(Xtr, ytr)
    print(f"\nExactitud del clasificador de perfil (prueba): {clf.score(Xte, yte):.3f}")

    if ruta_etiquetas:
        etiq = pd.read_csv(ruta_etiquetas).set_index("participante_id").reindex(feats.index)
        y = etiq.bfi2_responsabilidad
        print("\nResponsabilidad media (BFI-2) por perfil:\n", y.groupby(perfiles).agg(["mean", "std", "count"]).round(2).to_string())
        # ¿Predice el teléfono la etiqueta mejor que una línea base?
        from sklearn.ensemble import HistGradientBoostingRegressor
        pred = cross_val_predict(make_pipeline(RobustScaler(), HistGradientBoostingRegressor(max_depth=3, random_state=0)), X, y, cv=5)
        r = np.corrcoef(pred, y)[0, 1]
        print(f"\nCorrelación predicción vs. responsabilidad real (validación cruzada): r = {r:.3f}")

    salida = feats.assign(perfil=perfiles, prob_perfil=prob.round(3), baja_confianza=prob < 0.6)
    salida.to_csv("perfiles_resultado.csv")
    print("\nResultado por persona -> perfiles_resultado.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos_sinteticos.csv")
    ap.add_argument("--etiquetas", default=None)
    ap.add_argument("--k", type=int, default=None)
    a = ap.parse_args()
    main(a.datos, a.etiquetas, a.k)
