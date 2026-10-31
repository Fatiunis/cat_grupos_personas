"""Teléfonos simulados: generan eventos crudos como los de Android, minuto a minuto.

Cada persona sigue un arquetipo (horarios, intensidad, mezcla de apps, hábitos de carga).
La APK simulada después resume esos eventos con apk_resumen.py, igual que el teléfono real.
"""
import uuid
from datetime import datetime, timedelta

import numpy as np

from apk_resumen import (ACTIVITY_PAUSED, ACTIVITY_RESUMED, KEYGUARD_HIDDEN, SCREEN_INTERACTIVE,
                         SCREEN_NON_INTERACTIVE, Telefono)

# Paquetes por categoría; la APK los resuelve con Categories.of
PAQUETES = {
    "social": ["com.instagram.android", "com.zhiliaoapp.musically", "com.facebook.katana", "com.twitter.android"],
    "mensajeria": ["com.whatsapp", "org.telegram.messenger", "com.google.android.apps.messaging"],
    "juegos": ["com.supercell.clashroyale", "com.king.candycrushsaga", "com.activision.callofduty.shooter"],
    "video": ["com.google.android.youtube", "com.netflix.mediaclient", "tv.twitch.android.app"],
    "productividad": ["com.google.android.gm", "com.google.android.calendar", "com.microsoft.teams"],
    "educacion": ["com.duolingo", "com.google.android.apps.classroom"],
    "finanzas": ["com.bancolombia.app", "com.mercadopago.wallet"],
    "compras": ["com.mercadolibre", "com.amazon.mShop.android.shopping"],
    "otros": ["com.android.chrome", "com.google.android.apps.maps", "com.spotify.music"],
}

# despertar/dormir en horas locales (dormir > 24 = después de medianoche)
ARQUETIPOS = {
    "rutinario_moderado": dict(pantalla=180, sesiones=55, despertar=6.8, dormir=23.0, regularidad=0.85,
                               mezcla=dict(social=.25, mensajeria=.2, juegos=.03, video=.12, productividad=.15, educacion=.08, otros=.17),
                               notif=120, carga_nocturna=0.9, apps=70),
    "profesional_intensivo": dict(pantalla=360, sesiones=95, despertar=6.3, dormir=23.5, regularidad=0.8,
                                  mezcla=dict(social=.15, mensajeria=.3, juegos=.02, video=.08, productividad=.3, educacion=.05, otros=.1),
                                  notif=250, carga_nocturna=0.8, apps=110),
    "social_intenso": dict(pantalla=420, sesiones=140, despertar=8.0, dormir=25.0, regularidad=0.55,
                           mezcla=dict(social=.55, mensajeria=.2, juegos=.03, video=.12, productividad=.03, otros=.07),
                           notif=300, carga_nocturna=0.5, apps=95),
    "nocturno_irregular": dict(pantalla=360, sesiones=110, despertar=10.5, dormir=27.0, regularidad=0.3,
                               mezcla=dict(social=.4, mensajeria=.15, juegos=.1, video=.2, productividad=.03, otros=.12),
                               notif=180, carga_nocturna=0.3, apps=90),
    "usuario_minimo": dict(pantalla=90, sesiones=25, despertar=7.0, dormir=22.0, regularidad=0.85,
                           mezcla=dict(social=.1, mensajeria=.35, juegos=.02, video=.08, productividad=.1, finanzas=.05, otros=.3),
                           notif=40, carga_nocturna=0.7, apps=40),
    "gamer": dict(pantalla=300, sesiones=70, despertar=9.0, dormir=25.5, regularidad=0.5,
                  mezcla=dict(social=.1, mensajeria=.1, juegos=.5, video=.1, productividad=.02, otros=.18),
                  notif=100, carga_nocturna=0.4, apps=80),
}
MODELOS = ["Samsung SM-A155M", "Xiaomi 23129RAA4G", "Motorola moto g54 5G", "Google Pixel 7a", "OPPO CPH2591"]

MIN = 60_000


class Persona:
    def __init__(self, rng, arquetipo, zona, alta, consiente_notif=0.7, responde=0.75):
        self.rng = rng
        self.arquetipo = arquetipo
        self.p = ARQUETIPOS[arquetipo]
        self.nivel = rng.lognormal(0, 0.25)
        self.reg = float(np.clip(self.p["regularidad"] + rng.normal(0, 0.08), 0.05, 0.98))
        self.responde = responde
        cats = list(self.p["mezcla"])
        self.cats = cats
        self.mezcla = rng.dirichlet(np.array([self.p["mezcla"][c] for c in cats]) * 40)
        self.tel = Telefono(
            participante_id=str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)), version=4)),
            zona=zona,
            consiente_notificaciones=bool(rng.random() < consiente_notif),
            modelo=str(rng.choice(MODELOS)),
            version_android=int(rng.choice([29, 31, 33, 34, 35])),
            almacenamiento_libre_pct=float(np.clip(rng.normal(35, 15), 2, 90)),
            bloqueo_pantalla=bool(rng.random() < 0.85),
        )
        self.tel.categoria_de = {pkg: c for c, lista in PAQUETES.items() for pkg in lista}
        alta_ms = int(alta.timestamp() * 1000)
        n_apps = max(15, int(self.p["apps"] * rng.lognormal(0, 0.2)))
        self.tel.apps = [(f"app.{i}", alta_ms - int(rng.integers(1, 900)) * 86_400_000) for i in range(n_apps)]
        self.bateria = float(rng.uniform(50, 100))
        self.enchufado = False
        self.cursor = alta  # hasta dónde se generaron eventos
        self.ultimo_muestreo = int(alta.timestamp() * 1000)

    def vivir_dia(self, dia):
        """Genera los eventos del día que empieza al despertar de la fecha `dia` (datetime local)."""
        rng, p = self.rng, self.p
        jitter = 0.3 + 2.7 * (1 - self.reg)
        finde = dia.weekday() >= 5
        despertar = p["despertar"] + (1.2 if finde else 0) + rng.normal(0, jitter / 2)
        dormir = p["dormir"] + (0.8 if finde else 0) + rng.normal(0, jitter / 2)
        dormir = max(dormir, despertar + 8)
        t0 = dia + timedelta(hours=despertar)
        t1 = dia + timedelta(hours=dormir)
        objetivo = p["pantalla"] * self.nivel * (1.15 if finde else 1) * rng.lognormal(0, 0.15 + 0.35 * (1 - self.reg))
        n = max(3, rng.poisson(p["sesiones"] * self.nivel))
        # Duraciones lognormales que suman el objetivo; algunas muy cortas (mirar la hora)
        dur = rng.lognormal(0, 1.1, n)
        dur = dur / dur.sum() * objetivo
        cortas = rng.random(n) < 0.25
        dur[cortas] = rng.uniform(0.1, 0.45, cortas.sum())
        span = (t1 - t0).total_seconds() / 60
        inicios = np.sort(rng.uniform(0, span, n))
        eventos = self.tel.eventos
        fin_prev = -1.0
        for ini, d in zip(inicios, dur):
            ini = max(ini, fin_prev + 0.5)
            d = min(d, 240)
            a = int((t0 + timedelta(minutes=float(ini))).timestamp() * 1000)
            b = a + int(d * MIN)
            fin_prev = ini + d
            eventos.append((a, SCREEN_INTERACTIVE, None))
            if rng.random() < 0.9:
                eventos.append((a + 1500, KEYGUARD_HIDDEN, None))
            # Una o más apps en primer plano dentro de la sesión
            if d > 0.5:
                k = 1 + rng.poisson(min(3, d / 10))
                cortes = np.sort(rng.uniform(a + 3000, b - 1000, k - 1)).astype(int).tolist() if b - a > 5000 else []
                bordes = [a + 3000] + cortes + [b - 1000]
                for j in range(len(bordes) - 1):
                    cat = self.cats[rng.choice(len(self.cats), p=self.mezcla)]
                    pkg = str(rng.choice(PAQUETES[cat]))
                    eventos.append((bordes[j], ACTIVITY_RESUMED, pkg))
                    eventos.append((bordes[j + 1], ACTIVITY_PAUSED, pkg))
            eventos.append((b, SCREEN_NON_INTERACTIVE, None))
        # Notificaciones repartidas en el día despierto
        if self.tel.consiente_notificaciones:
            for _ in range(rng.poisson(p["notif"] * self.nivel)):
                self.tel.notificaciones.append(int((t0 + timedelta(minutes=float(rng.uniform(0, span)))).timestamp() * 1000))
        # Pregunta diaria (se guarda con la fecha en que se responde, como la APK)
        if rng.random() < self.responde:
            c = int(np.clip(round(rng.normal(2.5 + 2 * self.reg, 0.8)), 1, 5))
            punt = str(rng.choice(["si", "no", "na"], p=[0.4 + 0.4 * self.reg, 0.5 - 0.4 * self.reg, 0.1]))
            respondido = t0 + timedelta(hours=float(rng.uniform(12, 15)))  # tras el recordatorio de las 21:00
            self.tel.respuestas[respondido.date()] = (c, punt)
        self._muestrear_bateria(t0, t1, dia)
        if rng.random() < 0.02:  # instala una app nueva
            self.tel.apps.append((f"nueva.{len(self.tel.apps)}", int((t0 + timedelta(hours=3)).timestamp() * 1000)))
        eventos.sort(key=lambda e: e[0])

    def _muestrear_bateria(self, t0, t1, dia):
        """BatteryWorker: una muestra cada 15 min hasta el siguiente despertar."""
        rng = self.rng
        hasta = int((dia + timedelta(days=1, hours=self.p["despertar"])).timestamp() * 1000)
        a_ms, b_ms = int(t0.timestamp() * 1000), int(t1.timestamp() * 1000)
        carga_noche = rng.random() < self.p["carga_nocturna"]
        ons = [e[0] for e in self.tel.eventos if e[1] == SCREEN_INTERACTIVE and e[0] >= self.ultimo_muestreo]
        offs = [e[0] for e in self.tel.eventos if e[1] == SCREEN_NON_INTERACTIVE and e[0] >= self.ultimo_muestreo]
        sesiones = list(zip(ons, offs))
        ts = self.ultimo_muestreo + 15 * MIN
        while ts < hasta:
            despierto = a_ms <= ts < b_ms
            uso = sum(max(0, min(b, ts) - max(a, ts - 15 * MIN)) for a, b in sesiones) / MIN
            self.bateria -= 0.3 + 0.13 * uso
            if not self.enchufado and (self.bateria < 12 and rng.random() < 0.5 or (not despierto and ts >= b_ms and carga_noche)):
                self.enchufado = True
            if self.enchufado:
                self.bateria += 12
                if self.bateria >= 100 or (despierto and rng.random() < 0.3):
                    self.enchufado = False
            self.bateria = float(np.clip(self.bateria, 1, 100))
            red = "wifi" if (not despierto or rng.random() < 0.45) else ("movil" if rng.random() < 0.9 else "ninguna")
            self.tel.bateria.append((ts, int(self.bateria), self.enchufado, red))
            ts += 15 * MIN
        self.ultimo_muestreo = ts - 15 * MIN

    def olvidar_antes(self, ms):
        """Descarta datos ya resumidos para que la memoria no crezca (la APK recorta a 8 días)."""
        self.tel.eventos = [e for e in self.tel.eventos if e[0] >= ms]
        self.tel.bateria = [r for r in self.tel.bateria if r[0] >= ms]
        self.tel.notificaciones = [x for x in self.tel.notificaciones if x >= ms]


def nueva_persona(rng, zona, alta):
    nombres = list(ARQUETIPOS)
    pesos = np.array([0.25, 0.15, 0.20, 0.12, 0.13, 0.15])
    return Persona(rng, str(rng.choice(nombres, p=pesos)), zona, alta)


def medianoche(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)
