"""Carga datos sintéticos en la base para probar el dashboard.

Uso (desde backend/):
    python cargar_sinteticos.py --personas 300 --corrida

Las fechas se corren para que el último día sea ayer, así el dashboard muestra
participantes activos. También simula la pregunta diaria (q_cumplimiento, q_puntual),
que el generador de ml/ no incluye, con los mismos valores que la APK (1-5 y si/no/na), relacionada de forma débil con la etiqueta BFI-2.
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
from synthetic import generar  # noqa: E402

from app.analisis import ejecutar_corrida  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Corrida, Dia, Participante, ahora  # noqa: E402


def main(personas, dias, semilla, corrida, borrar):
    Base.metadata.create_all(engine)
    diario, etiq = generar(personas, dias, semilla)
    rng = np.random.default_rng(semilla)
    diario["fecha"] = pd.to_datetime(diario.fecha)
    diario["fecha"] = diario.fecha + (pd.Timestamp(date.today() - timedelta(days=1)) - diario.fecha.max())
    bfi = etiq.set_index("participante_id").bfi2_responsabilidad
    # Pregunta diaria: responde ~80 % de los días; el valor sigue a la responsabilidad con ruido
    responde = rng.random(len(diario)) < 0.8
    base = bfi.reindex(diario.participante_id).to_numpy()
    diario["q_cumplimiento"] = np.where(responde, np.clip(np.round(base + rng.normal(0, 0.9, len(diario))), 1, 5), np.nan)
    puntual = np.where(rng.random(len(diario)) < 0.1, "na", np.where(rng.random(len(diario)) < (base - 1) / 4, "si", "no"))
    diario["q_puntual"] = np.where(responde, puntual, None)

    with SessionLocal() as db:
        if borrar:
            for t in reversed(Base.metadata.sorted_tables):
                db.execute(t.delete())
        for pid, g in diario.groupby("participante_id"):
            ultimo = g.fecha.max().to_pydatetime()
            db.merge(Participante(id=pid, bfi2_responsabilidad=float(bfi[pid]), ultimo_envio=ultimo + timedelta(hours=27)))
            for fila in g.to_dict(orient="records"):
                f = fila.pop("fecha").date()
                fila.pop("participante_id")
                db.add(Dia(participante_id=pid, fecha=f, datos={k: (None if isinstance(v, float) and np.isnan(v) else v)
                                                                 for k, v in fila.items()}))
        db.commit()
        print(f"{len(diario)} días de {diario.participante_id.nunique()} personas cargados")
        if corrida:
            c = Corrida(resultado={})
            db.add(c)
            db.commit()
            cid = c.id
    if corrida:
        ejecutar_corrida(cid, SessionLocal)
        with SessionLocal() as db:
            c = db.get(Corrida, cid)
            print(f"Corrida {cid}: {c.estado} {c.error} k={c.k}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", type=int, default=300)
    ap.add_argument("--dias", type=int, default=42)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--corrida", action="store_true", help="corre el análisis al terminar")
    ap.add_argument("--borrar", action="store_true", help="vacía la base antes de cargar")
    a = ap.parse_args()
    main(a.personas, a.dias, a.semilla, a.corrida, a.borrar)
