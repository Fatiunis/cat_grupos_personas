from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def ahora():
    return datetime.now(timezone.utc)


class Participante(Base):
    __tablename__ = "participantes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    ultimo_envio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Excluido = no entra al análisis (prueba, datos dudosos), pero se conservan sus días
    excluido: Mapped[bool] = mapped_column(Boolean, default=False)
    notas: Mapped[str] = mapped_column(Text, default="")
    bfi2_responsabilidad: Mapped[float | None] = mapped_column(Float)


class Dia(Base):
    """Un resumen diario tal como lo envía la APK (DailySummary.kt)."""
    __tablename__ = "dias"
    __table_args__ = (UniqueConstraint("participante_id", "fecha"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participante_id: Mapped[str] = mapped_column(ForeignKey("participantes.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    recibido: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    datos: Mapped[dict] = mapped_column(JSON)


class Corrida(Base):
    """Una ejecución del pipeline de perfiles sobre los datos de ese momento."""
    __tablename__ = "corridas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creada: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    estado: Mapped[str] = mapped_column(String(16), default="corriendo")  # corriendo | lista | error
    k_pedido: Mapped[int | None] = mapped_column(Integer)
    k: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(Text, default="")
    # Métricas, tabla de selección de k, descripción y nombres de perfiles
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)


class Asignacion(Base):
    __tablename__ = "asignaciones"
    corrida_id: Mapped[int] = mapped_column(ForeignKey("corridas.id", ondelete="CASCADE"), primary_key=True)
    participante_id: Mapped[str] = mapped_column(ForeignKey("participantes.id", ondelete="CASCADE"), primary_key=True)
    perfil: Mapped[int] = mapped_column(Integer)
    prob: Mapped[float] = mapped_column(Float)
    x: Mapped[float] = mapped_column(Float)  # dos primeras componentes PCA, para el mapa
    y: Mapped[float] = mapped_column(Float)
