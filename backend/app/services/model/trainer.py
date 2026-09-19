"""Risk model trainer + scorer.

Trains an XGBoost (default) or RandomForest classifier on the landslide
inventory, persists it with joblib, records a ModelRun row for the
/admin/model/performance endpoint, and exposes fused (static-model + live
SWI) zone scoring used by both the API and the 30-minute Celery task.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import RiskLevel
from app.models.model_run import ModelRun
from app.models.risk import RiskScore
from app.models.zone import Zone
from app.services.model.features import (
    build_dataset,
    zone_feature_vector,
)
from app.services.swi.engine import refresh_zone_swi

logger = logging.getLogger(__name__)

MODEL_PATH = Path(settings.MODEL_PATH)
MODEL_DIR = MODEL_PATH.parent
METRICS_PATH = MODEL_PATH.with_suffix(".json")

_MODEL_CACHE: dict[str, Any] = {"model": None}


class ModelNotTrained(Exception):
    """Raised when scoring is requested before a model exists."""


LEVEL_THRESHOLDS = [
    (0.60, RiskLevel.red),
    (0.45, RiskLevel.orange),
    (0.30, RiskLevel.yellow),
]
DEFAULT_LEVEL = RiskLevel.green

STATIC_WEIGHT = 0.75
SWI_WEIGHT = 0.25


def probability_to_level(p: float) -> RiskLevel:
    """Map a fused risk probability to a RiskLevel."""
    for threshold, level in LEVEL_THRESHOLDS:
        if p >= threshold:
            return level
    return DEFAULT_LEVEL


def fuse_with_swi(static_p: float, swi: float) -> float:
    """Blend static model probability with live Soil Water Index.

    Wetter (higher SWI) raises the fused landslide probability.
    Returns a value in [0.005, 0.995].
    """
    fused = STATIC_WEIGHT * float(static_p) + SWI_WEIGHT * float(swi)
    return float(max(0.005, min(0.995, fused)))


def _stratified_split(
    X: np.ndarray, y: np.ndarray, test_size: float = 0.25, random_state: int = 42
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simple stratified train/test split (pure numpy, class-ratio preserved)."""
    rng = np.random.default_rng(random_state)

    def split_group(idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        idx = np.asarray(idx, dtype=np.int64)
        rng.shuffle(idx)
        n_test = max(1, int(round(len(idx) * test_size)))
        return idx[:n_test], idx[n_test:]

    test_pos, train_pos = split_group(np.where(y == 1)[0])
    test_neg, train_neg = split_group(np.where(y == 0)[0])

    train_idx = np.concatenate([train_pos, train_neg])
    test_idx = np.concatenate([test_pos, test_neg])
    rng.shuffle(test_idx)
    rng.shuffle(train_idx)

    return X[train_idx], X[test_idx], y[train_idx], y[test_idx]


def _evaluate(y_true: np.ndarray, y_proba: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Binary classification metrics in pure numpy (no scikit-learn needed)."""
    y_true = np.asarray(y_true, dtype=np.int64)
    y_pred = np.asarray(y_pred, dtype=np.int64)

    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))

    accuracy = round((tp + tn) / max(1, len(y_true)), 4)
    precision = round(tp / max(1, tp + fp), 4)
    recall = round(tp / max(1, tp + fn), 4)
    f1 = round(2 * precision * recall / max(1e-9, precision + recall), 4)

    # roc_auc via Mann-Whitney U with average-rank tie handling
    n_pos = int(np.sum(y_true == 1))
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        roc_auc = None
    else:
        order = np.argsort(y_proba, kind="mergesort")
        sorted_proba = y_proba[order]
        ranks = np.empty(len(y_proba), dtype=np.float64)
        i = 0
        while i < len(sorted_proba):
            j = i
            while j + 1 < len(sorted_proba) and sorted_proba[j + 1] == sorted_proba[i]:
                j += 1
            ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        sum_ranks_pos = float(np.sum(ranks[y_true == 1]))
        roc_auc = round(
            (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / max(1.0, n_pos * n_neg), 4
        )

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "roc_auc": roc_auc,
        "confusion_matrix": [[tn, fp], [fn, tp]],
    }


def model_exists() -> bool:
    return MODEL_PATH.exists()


def load_model() -> dict[str, Any]:
    """Load the persisted model (cached in-process)."""
    if _MODEL_CACHE["model"] is not None:
        return _MODEL_CACHE["model"]
    if not MODEL_PATH.exists():
        raise ModelNotTrained(
            f"Model not found at {MODEL_PATH} — run scripts/train_model.py first"
        )
    bundle = joblib.load(MODEL_PATH)
    _MODEL_CACHE["model"] = bundle
    return bundle


def reset_model_cache() -> None:
    _MODEL_CACHE["model"] = None


def predict_static_proba(zone: Zone, zones: list[Zone]) -> float:
    """Static (SWI-independent) landslide probability for a zone."""
    bundle = load_model()
    model = bundle["model"]
    feature_names = bundle["feature_names"]
    fv = zone_feature_vector(zone, zones)

    if bundle.get("model_type") == "xgboost":
        import xgboost as xgb
        dmat = xgb.DMatrix(fv.astype(np.float32), feature_names=feature_names)
        return float(model.predict(dmat)[0])
    else:
        return float(model.predict_proba(fv)[0][1])


def predict_zone_fused(db: Session, zone: Zone, zones: list[Zone]) -> float:
    """Full fused probability: static model + current SWI."""
    static_p = predict_static_proba(zone, zones)
    return fuse_with_swi(static_p, zone.swi_current or 0.0)


def train(
    db: Session,
    model_type: str = "xgboost",
    version: str | None = None,
) -> dict[str, Any]:
    """Train, evaluate, persist, record a ModelRun, and return metrics.

    Primary learner is XGBoost (native codec, works on all platforms).
    The RandomForest path additionally requires scikit-learn; on
    platforms where its compiled extensions are unavailable (e.g. strict
    Windows App Control policies) it raises a clear error.
    """
    X, y, feature_names = build_dataset(db)
    X_train, X_test, y_train, y_test = _stratified_split(
        X, y, test_size=0.25, random_state=42
    )

    model_name: str
    params: dict[str, Any]

    if model_type == "random_forest":
        try:
            from sklearn.ensemble import RandomForestClassifier
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "RandomForest path requires scikit-learn, which cannot be "
                "imported in this environment (App Control policy). Use "
                "--model xgboost instead."
            ) from exc
        clf = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        model_name = "RandomForest"
        params = {
            "n_estimators": 300,
            "max_depth": 8,
            "class_weight": "balanced",
        }
        clf.fit(X_train, y_train)
        y_proba = clf.predict_proba(X_test)[:, 1]
        booster = clf
    else:
        model_type = "xgboost"
        model_name = "XGBoost"
        import xgboost as xgb  # lazy: not installed on the Vercel function bundle
        params = {
            "max_depth": 6,
            "eta": 0.08,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "seed": 42,
        }
        dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_names)
        dtest = xgb.DMatrix(X_test, label=y_test, feature_names=feature_names)
        booster = xgb.train(
            params,
            dtrain,
            num_boost_round=300,
            evals=[(dtest, "test")],
            verbose_eval=False,
        )
        y_proba = booster.predict(dtest)

    y_pred = (y_proba >= 0.5).astype(np.int64)
    metrics_ = _evaluate(y_test, y_proba, y_pred)

    metrics = {
        "model_name": model_name,
        "version": version or settings.MODEL_VERSION,
        "accuracy": metrics_["accuracy"],
        "precision": metrics_["precision"],
        "recall": metrics_["recall"],
        "f1_score": metrics_["f1_score"],
        "roc_auc": metrics_["roc_auc"],
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "params": json.dumps(params),
        "confusion_matrix": json.dumps(metrics_["confusion_matrix"]),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": booster,
            "feature_names": feature_names,
            "version": metrics["version"],
            "model_type": model_type,
            "trained_at": metrics["trained_at"],
            "metrics": metrics,
        },
        MODEL_PATH,
    )
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    reset_model_cache()

    db.add(ModelRun(
        model_name=model_name,
        version=metrics["version"],
        accuracy=metrics["accuracy"],
        precision=metrics["precision"],
        recall=metrics["recall"],
        f1_score=metrics["f1_score"],
        roc_auc=metrics["roc_auc"],
        n_samples=metrics["n_samples"],
        n_features=metrics["n_features"],
        params=metrics["params"],
        confusion_matrix=metrics["confusion_matrix"],
        notes=f"Trained on landslide inventory; features={feature_names}",
    ))
    db.commit()

    logger.info(
        "Trained %s v%s — accuracy=%.3f f1=%.3f roc_auc=%.3f (n=%d)",
        model_name, metrics["version"], metrics["accuracy"],
        metrics["f1_score"], metrics["roc_auc"], metrics["n_samples"],
    )
    return metrics


def score_all_zones(db: Session, *, refresh_swi: bool = True) -> list[dict[str, Any]]:
    """Recompute SWI + fused risk probability for every zone.

    Upserts one RiskScore per zone (per-minute timestamp), and refreshes
    Zone.risk_level / risk_probability so the zones list shows real risk.
    """
    zones = list(db.scalars(select(Zone)).all())
    if not zones:
        return []

    # Ensure a model exists before doing anything
    load_model()

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    results: list[dict[str, Any]] = []

    for zone in zones:
        if refresh_swi:
            refresh_zone_swi(db, zone)

        fused_p = predict_zone_fused(db, zone, zones)
        level = probability_to_level(fused_p)

        existing = db.scalar(
            select(RiskScore).where(
                RiskScore.zone_id == zone.id,
                RiskScore.timestamp == now,
            )
        )
        if existing:
            existing.probability = fused_p
            existing.level = level
            existing.model_version = load_model().get("version")
        else:
            db.add(RiskScore(
                zone_id=zone.id,
                timestamp=now,
                probability=fused_p,
                level=level,
                model_version=load_model().get("version"),
            ))

        zone.risk_level = level
        zone.risk_probability = round(fused_p, 4)
        zone.last_updated = now

        results.append(
            {
                "zone_id": zone.id,
                "name": zone.name,
                "probability": round(fused_p, 4),
                "level": level.value,
            }
        )

    db.commit()
    return results


def latest_metrics(db: Session) -> dict[str, Any] | None:
    """Latest persisted ModelRun, or None."""
    run = db.scalar(select(ModelRun).order_by(ModelRun.id.desc()).limit(1))
    if run is None:
        return None
    return {
        "model_name": run.model_name,
        "version": run.version,
        "trained_at": run.trained_at,
        "accuracy": run.accuracy,
        "precision": run.precision,
        "recall": run.recall,
        "f1_score": run.f1_score,
        "roc_auc": run.roc_auc,
        "n_samples": run.n_samples,
        "n_features": run.n_features,
        "params": run.params,
        "confusion_matrix": run.confusion_matrix,
        "notes": run.notes,
    }