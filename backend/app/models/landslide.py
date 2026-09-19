from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import utcnow


class LandslideEvent(Base):
    __tablename__ = "landslide_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    geom_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)