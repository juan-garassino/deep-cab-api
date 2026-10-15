"""In-process state stores. Holds the active model, the background sample for
SHAP, and the train-task table. Multi-worker deployments swap these for Redis
(deferred to post-MVP); for single-worker dev they're enough."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class TaskRecord:
    """Status of one background training task."""

    task_id: str
    status: str = "pending"  # pending | running | succeeded | failed
    run_id: str | None = None
    error: str | None = None


@dataclass
class ModelHandle:
    """The fitted model served by the API.

    Attributes
    ----------
    estimator : AbstractEstimator
        Fitted backend.
    backend_kind : str
        Backend discriminator, e.g. "xgb".
    background : numpy.ndarray or None
        SHAP background sample, shape (n, 65), used by `/explain`.
    aci : ACIRegressor or None
        Conformal wrapper; None when calibration was skipped.
    """

    estimator: Any  # AbstractEstimator-like; kept Any to avoid eager import
    backend_kind: str
    background: np.ndarray | None = None
    aci: Any = None  # ACIRegressor when calibration succeeded; None otherwise


class _State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.model: ModelHandle | None = None
        self.tasks: dict[str, TaskRecord] = {}

    def set_model(self, handle: ModelHandle) -> None:
        """Replace the active model handle (thread-safe)."""
        with self.lock:
            self.model = handle

    def upsert_task(self, rec: TaskRecord) -> None:
        """Insert or replace a task record (thread-safe)."""
        with self.lock:
            self.tasks[rec.task_id] = rec


STATE = _State()
