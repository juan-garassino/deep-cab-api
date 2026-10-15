"""AbstractEstimator — the contract every backend implements.

Sklearn-compatible (BaseEstimator + RegressorMixin) so cross_validate, GridSearchCV,
and Pipeline accept it. Hyperparams live in a Pydantic BackendConfig instance owned
by the estimator; get_params/set_params bridge to/from cfg.model_dump() so sklearn
clone()-and-set semantics keep working.

For backends sklearn.clone() can't handle (TF, Torch, FT-T mixed state), use the
spec-as-factory pattern in deepCab.training.cv (mirrors 017's cv.py:14-48): rebuild
from cfg each fold instead of cloning."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel
from sklearn.base import BaseEstimator, RegressorMixin


class AbstractEstimator(BaseEstimator, RegressorMixin, ABC):
    """Base class. Each backend subclass declares cfg_cls (its Pydantic config) and
    implements _fit / _predict / _to_onnx. The framework methods handle sklearn
    plumbing + config round-tripping."""

    cfg_cls: type[BaseModel]  # set by subclass; the per-backend Pydantic config

    def __init__(self, **cfg_kwargs: Any) -> None:
        # Sklearn requires __init__ to store every constructor arg verbatim as an
        # attribute with the same name, with no validation. We honor that by
        # caching the raw kwargs; validation happens lazily in .cfg.
        self._cfg_kwargs = dict(cfg_kwargs)
        for k, v in cfg_kwargs.items():
            setattr(self, k, v)

    # --- sklearn contract -------------------------------------------------

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        """Return the raw constructor kwargs (sklearn contract); `deep` is ignored."""
        return dict(self._cfg_kwargs)

    def set_params(self, **params: Any) -> AbstractEstimator:
        """Update constructor kwargs and mirror them as attributes; returns `self`."""
        self._cfg_kwargs.update(params)
        for k, v in params.items():
            setattr(self, k, v)
        return self

    @property
    def cfg(self) -> BaseModel:
        """Validated Pydantic config built from current kwargs. Re-validates each
        access so set_params changes are honored."""
        return self.cfg_cls.model_validate(self._cfg_kwargs)

    def fit(self, X: np.ndarray, y: np.ndarray, **kw: Any) -> AbstractEstimator:
        """Fit the backend.

        Parameters
        ----------
        X : numpy.ndarray
            Features, shape (n_samples, n_features).
        y : numpy.ndarray
            Targets, shape (n_samples,) or (n_samples, 1); flattened to 1-D.
        **kw
            Backend-specific options such as `validation_data=(X_val, y_val)`.

        Returns
        -------
        AbstractEstimator
            `self`.
        """
        self._fit(np.asarray(X), np.asarray(y).ravel(), **kw)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict targets.

        Parameters
        ----------
        X : numpy.ndarray
            Features, shape (n_samples, n_features).

        Returns
        -------
        numpy.ndarray
            Predictions, shape (n_samples,).
        """
        return np.asarray(self._predict(np.asarray(X))).ravel()

    # --- backend hooks ----------------------------------------------------

    @abstractmethod
    def _fit(self, X: np.ndarray, y: np.ndarray, **kw: Any) -> None: ...

    @abstractmethod
    def _predict(self, X: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def save(self, path: Path) -> None:
        """Persist the fitted model at `path` (a file or a directory, depending on the backend)."""

    @classmethod
    @abstractmethod
    def load(cls, path: Path) -> AbstractEstimator:
        """Rebuild a fitted estimator from what `save` wrote at `path`."""

    def to_onnx(self, path: Path, sample: np.ndarray) -> Path:
        """Per-backend ONNX export lands in Phase 3 (deepCab/models/onnx_export.py)."""
        raise NotImplementedError(f"ONNX export for {type(self).__name__} arrives in Phase 3")
