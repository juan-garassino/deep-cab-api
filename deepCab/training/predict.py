"""Single-row + batch predict. The agent's `predict` tool calls these; the
FastAPI `/predict` router (Phase 6) calls these too."""

from __future__ import annotations

import numpy as np
import pandas as pd

from deepCab.features.pipeline import preprocess_features
from deepCab.models.base import AbstractEstimator
from deepCab.schemas.data import FeatureRow


def predict_one(estimator: AbstractEstimator, row: FeatureRow) -> float:
    """Preprocess one `FeatureRow` and return the fare as a float."""
    X = preprocess_features(pd.DataFrame([row.model_dump()]))
    return float(np.asarray(estimator.predict(X)).ravel()[0])


def predict_many(estimator: AbstractEstimator, rows: list[FeatureRow]) -> list[float]:
    """Preprocess and predict many rows in one pass; an empty list yields an empty list."""
    if not rows:
        return []
    X = preprocess_features(pd.DataFrame([r.model_dump() for r in rows]))
    return [float(v) for v in np.asarray(estimator.predict(X)).ravel()]
