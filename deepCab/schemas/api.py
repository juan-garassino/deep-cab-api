"""FastAPI request/response models. Share the same FeatureRow as the training pipeline,
and the same TrainConfig the agent's `train` tool will accept — single source of truth."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from deepCab.schemas.config import TrainConfig
from deepCab.schemas.data import FeatureRow
from deepCab.schemas.enums import ExplainMode, RunStatus


class PredictRequest(BaseModel):
    """Body of `POST /predict`."""

    model_config = ConfigDict(extra="forbid")

    row: FeatureRow


class PredictResponse(BaseModel):
    """Predicted fare, with interval bounds when a conformal wrapper is active."""

    model_config = ConfigDict(extra="forbid")

    fare: float
    interval_lower: float | None = None  # populated when conformal wrapper active
    interval_upper: float | None = None
    backend_kind: str


class BatchPredictRequest(BaseModel):
    """Body of `POST /predict/batch` (1 to 10,000 rows)."""

    model_config = ConfigDict(extra="forbid")

    rows: Annotated[list[FeatureRow], Field(min_length=1, max_length=10_000)]


class BatchPredictResponse(BaseModel):
    """One `PredictResponse` per input row, in order."""

    model_config = ConfigDict(extra="forbid")

    predictions: list[PredictResponse]


class ExplainRequest(BaseModel):
    """Body of `POST /explain`."""

    model_config = ConfigDict(extra="forbid")

    row: FeatureRow
    mode: ExplainMode = ExplainMode.PER_ROW


class ExplainResponse(BaseModel):
    """SHAP prediction, base value and attribution per feature group."""

    model_config = ConfigDict(extra="forbid")

    prediction: float
    base_value: float
    shap_by_feature: dict[str, float]  # aggregated to the 6 user features


class TrainStartRequest(BaseModel):
    """Body of `POST /train`."""

    model_config = ConfigDict(extra="forbid")

    config: TrainConfig


class TrainStartResponse(BaseModel):
    """Handle of the queued training task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str


class TrainStatusResponse(BaseModel):
    """Status of a training task, with the MLflow run id or the error."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: RunStatus
    run_id: str | None = None
    error: str | None = None
