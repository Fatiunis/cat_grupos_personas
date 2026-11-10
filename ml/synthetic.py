"""Generador de datos sintéticos de uso de teléfono.

Simula una fila por persona y día con el mismo esquema que enviará la APK.
Sirve para probar el pipeline, no para entrenar el modelo final.

Uso:
    python synthetic.py --personas 2000 --dias 42 --salida datos_sinteticos.csv
"""
import argparse

import numpy as np
import pandas as pd

# Parámetros por arquetipo. Tiempos en minutos u horas, conteos por día.
# "regularidad" (0-1) controla cuánto varían los horarios de un día a otro.
ARQUETIPOS = {
    "rutinario_moderado": dict(
        pantalla=180, desbloqueos=50, social=0.25, mensajeria=0.20, juegos=0.03, video=0.12,
        productividad=0.15, educacion=0.08, primer_uso=6.8, ultimo_uso=22.8, noche=5,
        regularidad=0.85, bateria_baja=0.10, cargas=1.2, apps=70, notificaciones=120,
        pasos=7000, lugares=3.0, horas_casa=13),
    "profesional_intensivo": dict(
        pantalla=360, desbloqueos=90, social=0.15, mensajeria=0.30, juegos=0.02, video=0.08,
        productividad=0.30, educacion=0.05, primer_uso=6.3, ultimo_uso=23.3, noche=10,
        regularidad=0.80, bateria_baja=0.15, cargas=1.8, apps=110, notificaciones=250,
        pasos=6000, lugares=4.0, horas_casa=11),
    "social_intenso": dict(
        pantalla=420, desbloqueos=140, social=0.55, mensajeria=0.20, juegos=0.03, video=0.12,
        productividad=0.03, educacion=0.02, primer_uso=8.0, ultimo_uso=24.8, noche=40,
        regularidad=0.55, bateria_baja=0.40, cargas=2.2, apps=95, notificaciones=300,
        pasos=5000, lugares=3.5, horas_casa=14),
    "nocturno_irregular": dict(
        pantalla=360, desbloqueos=110, social=0.40, mensajeria=0.15, juegos=0.10, video=0.20,
        productividad=0.03, educacion=0.02, primer_uso=10.5, ultimo_uso=27.0, noche=120,
        regularidad=0.30, bateria_baja=0.60, cargas=2.0, apps=90, notificaciones=180,
        pasos=3500, lugares=2.0, horas_casa=17),
    "usuario_minimo": dict(
        pantalla=90, desbloqueos=25, social=0.10, mensajeria=0.35, juegos=0.02, video=0.08,
        productividad=0.10, educacion=0.05, primer_uso=7.0, ultimo_uso=22.0, noche=0,
        regularidad=0.85, bateria_baja=0.25, cargas=0.8, apps=40, notificaciones=40,
        pasos=8000, lugares=3.0, horas_casa=12),
    "gamer": dict(
        pantalla=300, desbloqueos=70, social=0.10, mensajeria=0.10, juegos=0.50, video=0.10,
        productividad=0.02, educacion=0.02, primer_uso=9.0, ultimo_uso=25.5, noche=60,
        regularidad=0.50, bateria_baja=0.45, cargas=2.0, apps=80, notificaciones=100,
        pasos=3000, lugares=1.8, horas_casa=18),
}
CATEGORIAS = ["social", "mensajeria", "juegos", "video", "productividad", "educacion"]

# Calibración "estudios": los mismos arquetipos, ajustados a cifras publicadas.
# Fuentes (detalle y links en el informe del proyecto):
#  - Andrews et al. 2015: ~85 revisiones y ~5 h de uso al día; más de la mitad de los usos < 30 s.
#  - Bentley et al. 2015: dispersión grande entre personas (173.6 min, DE 129.7); la comunicación
#    es cerca de dos tercios del uso y los juegos son una parte pequeña para la mayoría.
#  - dscout 2016: 76 sesiones al día en promedio, 132 en el 10 % más intenso.
#  - Böhmer et al. 2011: juegos y redes tienen su pico de noche; el uso mínimo es cerca de las 5 am.
#  - Stachl et al. 2020: la responsabilidad se asocia a primer y último uso más tempranos y a una
#    inactividad nocturna más regular; se predice con r de 0.31, una relación modesta.
#  - Marengo et al. 2020: responsabilidad y uso problemático, r = -0.16.
#  - Buzoku et al. 2025 y Guerreiro et al. 2024: responsabilidad y matutinidad, efecto de 0.16 a 0.35.
CALIBRACIONES = ("base", "estudios")
_MEDIA_PANTALLA = 215  # queda en ~255 min/día ya con fines de semana y variación diaria: entre Bentley (~174) y Andrews (~300)
_MEDIA_DESBLOQUEOS = 72  # queda en ~82 al día, cerca de las ~85 revisiones de Andrews
_ACERCAR = 0.4  # cuánto se acercan los arquetipos al promedio: más mezcla entre grupos
_EFECTO_RASGO = 0.37  # fuerza del rasgo sobre el uso; con 0.37 el modelo lo recupera con r ~0.3 (Stachl)


def _arquetipos_estudios():
    pesos = np.array([0.25, 0.15, 0.20, 0.12, 0.13, 0.15])
    nombres = list(ARQUETIPOS)
    medias = {c: float(np.dot(pesos, [ARQUETIPOS[n][c] for n in nombres])) for c in ARQUETIPOS[nombres[0]]}
    salida = {}
    for n in nombres:
        a = {c: v + _ACERCAR * (medias[c] - v) for c, v in ARQUETIPOS[n].items()}
        a["pantalla"] *= _MEDIA_PANTALLA / medias["pantalla"]
        a["desbloqueos"] *= _MEDIA_DESBLOQUEOS / medias["desbloqueos"]
        salida[n] = a
    return salida


ARQUETIPOS_ESTUDIOS = _arquetipos_estudios()


# Las horas son continuas desde la medianoche del día, como en la APK:
# el día va de 05:00 a 05:00, así que el último uso puede ir de 5 a 29 h
# y el inicio de sueño (medido de 18:00 a 14:00 del día siguiente) de 18 a 38 h.
def _hora(h, minimo=5.0, maximo=29.0):
    return float(np.clip(h, minimo, maximo))


def simular_persona(rng, pid, arquetipo, dias, inicio, tabla=None, rasgo=0.0):
    """rasgo: responsabilidad latente de la persona (0 = promedio). Solo la usa la calibración
    "estudios", donde desplaza un poco horarios, regularidad, uso nocturno y mezcla de apps."""
    base = dict((tabla or ARQUETIPOS)[arquetipo])
    if rasgo:
        rasgo *= _EFECTO_RASGO
        base["primer_uso"] -= 0.35 * rasgo
        base["ultimo_uso"] -= 0.35 * rasgo
        base["regularidad"] += 0.06 * rasgo
        base["noche"] *= float(np.exp(-0.3 * rasgo))
        base["bateria_baja"] *= float(np.exp(-0.25 * rasgo))
        base["productividad"] *= float(np.exp(0.2 * rasgo))
        base["juegos"] *= float(np.exp(-0.2 * rasgo))
    # Efecto propio de la persona: nadie es el arquetipo exacto.
    nivel = rng.lognormal(0, 0.45 if tabla else 0.25)
    reg = float(np.clip(base["regularidad"] + rng.normal(0, 0.08), 0.05, 0.98))
    jitter_h = 0.3 + 2.7 * (1 - reg)  # horas de variación diaria en horarios
    mezcla = rng.dirichlet(np.array([base[c] for c in CATEGORIAS]) * 40)
    apps = max(15, int(base["apps"] * rng.lognormal(0, 0.2)))

    filas = []
    for d in range(dias):
        fecha = inicio + pd.Timedelta(days=d)
        finde = fecha.dayofweek >= 5
        if rng.random() < 0.12:  # día sin reporte (app detenida, teléfono apagado)
            continue
        f_finde = 1.15 if finde else 1.0
        pantalla = base["pantalla"] * nivel * f_finde * rng.lognormal(0, 0.15 + 0.35 * (1 - reg))
        pantalla = min(pantalla, 1200)
        desbloqueos = rng.poisson(base["desbloqueos"] * nivel * f_finde)
        sesion_media = pantalla / max(desbloqueos, 1)
        p_corta = 0.55 if tabla else min(0.9, 0.25 + 0.003 * base["desbloqueos"])
        cortas = rng.binomial(max(desbloqueos, 0), p_corta)
        primer = _hora(base["primer_uso"] + (1.2 if finde else 0) + rng.normal(0, jitter_h))
        ultimo = _hora(base["ultimo_uso"] + (0.8 if finde else 0) + rng.normal(0, jitter_h))
        noche = max(0.0, base["noche"] * nivel * rng.lognormal(0, 0.6) * (1.5 if finde else 1))
        inicio_sueno = _hora(ultimo + rng.uniform(0.1, 0.6), 18.0, 38.0)
        bajas = rng.poisson(base["bateria_baja"] * (2 - reg))
        bateria_min = float(np.clip(rng.normal(8 if bajas else 35, 10), 1, 95))
        mix_dia = rng.dirichlet(mezcla * 200)
        fila = dict(
            participante_id=pid, fecha=fecha.date(), arquetipo=arquetipo,
            pantalla_min=round(pantalla, 1), desbloqueos=int(desbloqueos),
            sesion_media_min=round(sesion_media, 2), sesiones_cortas=int(cortas),
            hora_primer_uso=round(primer, 2), hora_ultimo_uso=round(ultimo, 2),
            uso_nocturno_min=round(noche, 1), hora_inicio_sueno=round(inicio_sueno, 2),
            bateria_min_pct=round(bateria_min, 1), veces_bateria_baja=int(bajas),
            cargas=int(rng.poisson(base["cargas"])),
            carga_nocturna=int(rng.random() < 0.3 + 0.6 * reg),
            apps_instaladas=apps, apps_nuevas=int(rng.poisson(0.15)),
            notificaciones=int(rng.poisson(base["notificaciones"] * nivel)),
            pasos=int(base["pasos"] * rng.lognormal(0, 0.35) * (0.8 if finde else 1)),
            lugares_distintos=int(max(1, rng.poisson(base["lugares"] * (1.2 - 0.4 * (1 - reg))))),
            horas_en_casa=round(float(np.clip(rng.normal(base["horas_casa"], 2), 4, 24)), 1),
        )
        for c, p in zip(CATEGORIAS, mix_dia):
            fila[f"{c}_min"] = round(pantalla * p, 1)
        # Valor atípico ocasional (error de medición o día extremo)
        if rng.random() < 0.01:
            fila["pantalla_min"] = round(fila["pantalla_min"] * 3, 1)
        filas.append(fila)
    return filas, reg


def generar(personas=2000, dias=42, semilla=7, calibracion="base"):
    if calibracion not in CALIBRACIONES:
        raise ValueError(f"calibracion debe ser una de {CALIBRACIONES}")
    if calibracion == "estudios":
        return _generar_estudios(personas, dias, semilla)
    rng = np.random.default_rng(semilla)
    inicio = pd.Timestamp("2026-01-05")
    nombres = list(ARQUETIPOS)
    pesos = np.array([0.25, 0.15, 0.20, 0.12, 0.13, 0.15])
    filas, etiquetas = [], []
    for i in range(personas):
        arq = rng.choice(nombres, p=pesos)
        pid = f"p{i:05d}"
        f, reg = simular_persona(rng, pid, arq, dias, inicio)
        filas.extend(f)
        # Etiqueta sintética de responsabilidad (escala 1-5 tipo BFI-2), con relación
        # débil y ruidosa con la regularidad, para que las expectativas sean realistas.
        base = ARQUETIPOS[arq]
        latente = 0.8 * (reg - 0.6) - 0.002 * (base["noche"] - 40) + 0.6 * (base["productividad"] - 0.1)
        bfi = float(np.clip(3.4 + latente + rng.normal(0, 0.6), 1, 5))
        etiquetas.append(dict(participante_id=pid, arquetipo=arq, bfi2_responsabilidad=round(bfi, 2)))
    return pd.DataFrame(filas), pd.DataFrame(etiquetas)


def _generar_estudios(personas, dias, semilla):
    """Responsabilidad como rasgo de cada persona (no del arquetipo), con efectos pequeños
    sobre el uso, para que la relación quede en el orden de lo publicado (r cerca de 0.3)."""
    rng = np.random.default_rng(semilla)
    inicio = pd.Timestamp("2026-01-05")
    nombres = list(ARQUETIPOS)
    pesos = np.array([0.25, 0.15, 0.20, 0.12, 0.13, 0.15])
    filas, etiquetas = [], []
    for i in range(personas):
        arq = rng.choice(nombres, p=pesos)
        pid = f"p{i:05d}"
        rasgo = float(rng.normal())
        f, _ = simular_persona(rng, pid, arq, dias, inicio, ARQUETIPOS_ESTUDIOS, rasgo)
        filas.extend(f)
        bfi = float(np.clip(3.5 + 0.65 * rasgo, 1, 5))
        etiquetas.append(dict(participante_id=pid, arquetipo=arq, bfi2_responsabilidad=round(bfi, 2)))
    return pd.DataFrame(filas), pd.DataFrame(etiquetas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", type=int, default=2000)
    ap.add_argument("--dias", type=int, default=42)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--calibracion", choices=CALIBRACIONES, default="base")
    ap.add_argument("--salida", default="datos_sinteticos.csv")
    ap.add_argument("--etiquetas", default="etiquetas_sinteticas.csv")
    a = ap.parse_args()
    diario, etiq = generar(a.personas, a.dias, a.semilla, a.calibracion)
    diario.to_csv(a.salida, index=False)
    etiq.to_csv(a.etiquetas, index=False)
    print(f"{len(diario)} filas diarias de {diario.participante_id.nunique()} personas -> {a.salida}")
