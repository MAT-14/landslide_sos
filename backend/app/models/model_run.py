from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import utcnow


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50), index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    n_features: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confusion_matrix: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)