"""Simulador de teléfonos con la APK instalada.

Reproduce lo que hace DailyWorker: cada día, alrededor de las 03:00, arma el resumen de
los días pendientes (hasta 6 atrás), los encola y los envía uno por uno con POST a
INGEST_URL. Si no recibe 2xx, el día queda en la cola y se reintenta al día siguiente.

Ejemplos:
    # 50 personas con 21 días de historia, enviados de golpe
    python simulador.py --url http://localhost:8000/ingest --personas 50 --historia 21

    # Además, en vivo: un día simulado cada 20 s y 2 personas nuevas por día
    python simulador.py --url http://localhost:8000/ingest --personas 30 --historia 14 \
        --en-vivo --segundos-por-dia 20 --altas-por-dia 2

    # Sin servidor: solo escribe los JSON que enviaría la APK
    python simulador.py --personas 300 --historia 28 --salida enviados.jsonl
"""
import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from apk_resumen import resumen_diario
from dispositivo import medianoche, nueva_persona


class Apk:
    """Estado local de la APK en un teléfono: días enviados y cola pendiente."""

    def __init__(self, persona):
        self.persona = persona
        self.enviados = set()
        self.cola = {}

    def worker_diario(self, hoy, enviar):
        tel = self.persona.tel
        for d in range(6, 0, -1):
            fecha = hoy - timedelta(days=d)
            if fecha < self.persona.alta.date() or fecha in self.enviados or fecha in self.cola:
                continue
            self.cola[fecha] = resumen_diario(tel, fecha)
            if ARGS.con_arquetipo:  # solo para QA: permite medir el ARI del pipeline
                self.cola[fecha]["arquetipo"] = self.persona.arquetipo
        for fecha in sorted(self.cola):
            codigo = enviar(self.cola[fecha])
            if codigo is not None and 200 <= codigo < 300:
                if random.random() >= ARGS.respuesta_perdida:
                    self.enviados.add(fecha)
                    del self.cola[fecha]
                # si no, el servidor guardó pero el teléfono no se enteró y reenviará
        lim = medianoche(datetime.combine(hoy, datetime.min.time(), tel.zona)) - timedelta(days=8)
        self.persona.olvidar_antes(int(lim.timestamp() * 1000))


class Enviador:
    def __init__(self, url, token, salida):
        self.url, self.token = url, token
        self.salida = open(salida, "a") if salida else None
        self.conteo = {}

    def __call__(self, payload):
        cuerpo = json.dumps(payload).encode()
        codigo = None
        if not self.url:
            codigo = 200  # modo solo local, como INGEST_URL vacío
        else:
            req = urllib.request.Request(self.url, data=cuerpo, method="POST",
                                         headers={"Content-Type": "application/json"})
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    codigo = r.status
            except urllib.error.HTTPError as e:
                codigo = e.code
            except (urllib.error.URLError, OSError):
                codigo = None
        self.conteo[codigo] = self.conteo.get(codigo, 0) + 1
        if self.salida:
            self.salida.write(json.dumps({"codigo": codigo, "payload": payload}) + "\n")
            self.salida.flush()
        return codigo


def malformados(enviar):
    """Envíos que el backend debería rechazar con 4xx."""
    casos = {
        "sin participante_id": {"fecha": "2026-01-01", "pantalla_min": 10},
        "sin fecha": {"participante_id": "x", "pantalla_min": 10},
        "fecha inválida": {"participante_id": "x", "fecha": "2026-13-45"},
    }
    for nombre, p in casos.items():
        print(f"  malformado ({nombre}) -> {enviar(p)}")


def main():
    zona = ZoneInfo(ARGS.zona)
    rng = np.random.default_rng(ARGS.semilla)
    random.seed(ARGS.semilla)
    enviar = Enviador(ARGS.url, ARGS.token, ARGS.salida)
    if ARGS.malformados:
        malformados(enviar)

    ahora = medianoche(datetime.now(zona))
    inicio = ahora - timedelta(days=ARGS.historia)
    apks = []

    def alta(cuando):
        p = nueva_persona(rng, zona, cuando)
        p.alta = cuando
        apks.append(Apk(p))

    for _ in range(ARGS.personas):
        alta(inicio)

    def un_dia(dia, pausa_total=0.0):
        for a in apks:
            a.persona.vivir_dia(dia)
        hoy = (dia + timedelta(days=1)).date()
        orden = list(apks)
        random.shuffle(orden)
        for a in orden:
            if random.random() >= ARGS.sin_red:  # NetworkType.CONNECTED
                a.worker_diario(hoy, enviar)
            if pausa_total:
                time.sleep(pausa_total / len(orden))
        print(f"{hoy}  teléfonos={len(apks)}  respuestas={dict(sorted(enviar.conteo.items(), key=str))}", flush=True)

    dia = inicio
    while dia < ahora:
        un_dia(dia)
        dia += timedelta(days=1)
    if not ARGS.en_vivo:
        return
    print(f"En vivo: un día simulado cada {ARGS.segundos_por_dia} s (Ctrl+C para parar)", flush=True)
    while ARGS.dias_en_vivo == 0 or (dia - ahora).days < ARGS.dias_en_vivo:
        for _ in range(ARGS.altas_por_dia):
            alta(dia)
        un_dia(dia, ARGS.segundos_por_dia)
        dia += timedelta(days=1)


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="", help="INGEST_URL; vacío = solo local")
    ap.add_argument("--token", default="", help="INGEST_TOKEN (Authorization: Bearer)")
    ap.add_argument("--personas", type=int, default=30)
    ap.add_argument("--historia", type=int, default=14, help="días ya transcurridos desde la instalación")
    ap.add_argument("--en-vivo", action="store_true")
    ap.add_argument("--segundos-por-dia", type=float, default=20)
    ap.add_argument("--dias-en-vivo", type=int, default=0, help="0 = sin fin")
    ap.add_argument("--altas-por-dia", type=int, default=1)
    ap.add_argument("--sin-red", type=float, default=0.08, help="probabilidad de que el worker no corra un día")
    ap.add_argument("--respuesta-perdida", type=float, default=0.03, help="probabilidad de reenviar un día ya guardado")
    ap.add_argument("--malformados", action="store_true", help="envía casos inválidos al inicio")
    ap.add_argument("--con-arquetipo", action="store_true", help="agrega el arquetipo verdadero (solo QA)")
    ap.add_argument("--zona", default="America/Bogota")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--salida", default="", help="archivo JSONL con cada envío y su código")
    return ap.parse_args(argv)


if __name__ == "__main__":
    ARGS = argumentos()
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
