# deepCab

NYC taxi-fare prediction used as a learning hub for MLOps. The repo covers model training, a FastAPI service, an OpenAI tool-calling agent, orchestration and a Docker Compose observability stack in one package (`deepCab/`).

> **GCP migration note (2026-06-07):** the GCP project `deepcab-dev` was deleted. The project now deploys on demand to `garassino-ml` (region `europe-west1`). Images are on `ghcr.io/juan-garassino/deepcab-{api,website}`. References to `deepcab-dev` or `us-central1` in `docs/` describe the state before the migration.

## What is in it

| Area | What it does | Code |
|---|---|---|
| Models | 6 backends behind one sklearn-style interface: TF MLP, Torch MLP, XGBoost, LightGBM, CatBoost, FT-Transformer | `deepCab/models/` |
| Config | Pydantic schemas shared by FastAPI bodies, agent tool parameters, Hydra configs and MLflow params | `deepCab/schemas/` |
| Data | Polars + DuckDB, Hive-partitioned Parquet, Pandera validation, SQLite lineage | `deepCab/data/` |
| Training | Hydra entry point, Optuna HPO, time-series CV, conformal prediction intervals (ACI) | `deepCab/training/`, `deepCab/models/conformal.py` |
| Serving | FastAPI (REST, SSE, GraphQL), optional gRPC, ONNX runtime with INT8 quantization | `deepCab/api/`, `deepCab/serving/`, `deepCab/grpc/` |
| Explainability | SHAP attributions aggregated to 5 feature groups | `deepCab/explain/` |
| Agent | Planner/executor over 9 tools, budget cap, JSONL trace | `deepCab/agent/` |
| Orchestration | Prefect 3 retrain and simulation flows, MLflow aliases (`champion`/`challenger`), generated `MODEL_CARD.md` | `deepCab/flow_v2/`, `deepCab/registry/` |
| Infra | Compose stacks (core, observability, GPU), Cloud Run/GKE deploy workflows, CI | `infra/`, `.github/workflows/` |

## Quickstart (CPU)

Needs Python 3.10 or 3.11 and [uv](https://docs.astral.sh/uv/). The commands below were run end to end on Linux/CPU while preparing this README.

```bash
uv sync --extra dev

# Data: 1k training rows from the public `datascience-mlops` bucket used by the Makefile, 10k validation rows shipped in this repo
mkdir -p ~/.lewagon/mlops/data/raw
curl -sSo ~/.lewagon/mlops/data/raw/train_1k.csv \
  https://storage.googleapis.com/datascience-mlops/taxi-fare-ny/train_1k.csv
uv run python -m deepCab.data.migrate --size 1k  --split train
uv run python -m deepCab.data.migrate --size 10k --split val --src deepCab/data

# Train (about 15 s) and serve
uv run python -m deepCab.training.train backend=xgb data=1k data.validation_size=10k
uv run uvicorn deepCab.api.app:app --port 8000
```

The training run logs `val_mae` (2.46 for this command in a CPU sandbox run, seed 42) and saves the model under `~/.lewagon/mlops/training_outputs/runs/`. On startup the API reloads the last run from there, so `/readyz` reports `model_loaded: true`.

```bash
ROW='{"row":{"pickup_datetime":"2014-01-15T05:00:00","pickup_longitude":-73.97,"pickup_latitude":40.78,"dropoff_longitude":-73.99,"dropoff_latitude":40.74,"passenger_count":2}}'
curl -X POST localhost:8000/predict -H 'Content-Type: application/json' -d "$ROW"
# {"fare":13.77,"interval_lower":8.62,"interval_upper":18.92,"backend_kind":"xgb"}
```

Interactive docs are at `http://localhost:8000/docs`.

Why validation uses a different size than training: `deepCab.data.migrate` writes `train` and `val` of the same size into the same Parquet partition files, so the second call overwrites the first (see "Known issues"). Using two sizes avoids it.

## API

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /`, `/version`, `/healthz`, `/readyz`, `/metrics` | none | `/readyz` reports `model_loaded` and `backend_kind` |
| `POST /predict`, `/predict/batch`, `/predict/stream` | none | Fare plus conformal interval when calibrated. **Without a loaded model these return a distance-based stub fare with `backend_kind: "random-stub"`** |
| `POST /explain`, `GET /explain/summary` | none | SHAP by group; 503 when no model is loaded, 409 when the model has no background sample |
| `POST /train`, `GET /train/{task_id}` | `X-API-Key` | Background training; poll the task id |
| `POST /agent`, `POST /agent/improve` | `X-API-Key` | SSE; needs an OpenAI key |
| `/graphql` | `X-API-Key` | `predict`, `listRuns`, `version`, `train` mutation |

The key is checked against `DEEPCAB_API_KEY` (falls back to `OPENAI_API_KEY`). With neither set the gated endpoints are open, which is the development default.

Train a different backend through the API (this call was run; the `lgbm` model then served `/predict` and `/explain`):

```bash
curl -X POST localhost:8000/train -H 'Content-Type: application/json' \
  -d '{"config":{"backend":{"kind":"lgbm","n_estimators":200},"data":{"size":"1k","validation_size":"10k"},"seed":42}}'
# {"task_id":"..."}   then: curl localhost:8000/train/<task_id>
```

Add `-H "X-API-Key: $KEY"` when a key is configured.

## Training options

```bash
# Hydra overrides: any field of the backend config
uv run python -m deepCab.training.train backend=lgbm backend.num_leaves=63 backend.learning_rate=0.03
# other dataset sizes
uv run python -m deepCab.training.train backend=xgb data.size=10k data.validation_size=10k seed=7
```

Backends: `tf_mlp` (default), `torch_mlp`, `xgb`, `lgbm`, `catboost`, `ft_transformer`. Only `data/1k.yaml` exists as a Hydra data preset, so other sizes are set with `data.size` and `data.validation_size`. A Typer CLI wraps the same entry points: `uv run deepcab --help`.

## Agent

Not run in this README pass because it needs an OpenAI key.

```bash
# key in .env.dev (OPENAI_API_KEY) or infra/secrets/openai_api_key
uv run python -m deepCab.agent.cli
> /improve reduce val_mae below 3.0
```

Tools: `preprocess`, `train`, `evaluate`, `predict`, `explain`, `tune`, `list_runs`, `compare_runs`, `propose_next_experiment`. Each tool's Pydantic input model is also its OpenAI schema (`deepCab/agent/tools.py`). `POST /agent/improve` takes a required budget (`max_iters`, `max_tool_calls`, `max_usd`).

## Orchestration

```bash
make run_flow     # one retrain in-process (Prefect 3); not run in this pass
make flow_serve   # nightly schedule
```

## Full stack with Docker Compose

Not run in this README pass (no Docker in the sandbox). Files are under `infra/compose/`; see `infra/README.md` for the one-time secrets and TLS setup.

```bash
make docker_up        # traefik, api, mlflow, postgres, minio, redis, prefect
make docker_obs_up    # + otel, jaeger, prometheus, alertmanager, grafana, loki, promtail
make docker_gpu_up    # GPU override; needs nvidia-container-toolkit
```

Grafana provisions three dashboards (API, Agent, Training). Alert rules are in `infra/compose/conf/prometheus-rules.yml`. Slack alerts use `infra/secrets/slack_webhook_url`.

## Deploy

Cloud Run, GKE and Cloud Run Job workflows are in `.github/workflows/`; setup notes are in `infra/gcp/` and the sibling `002-deepCab-platform` repo. They use OIDC (no long-lived keys). GKE deploys are dispatch-only.

## Tests

```bash
uv run pytest tests/ -q
uv run ruff format --check . && uv run ruff check .
```

Result of this pass (CPU sandbox, `uv sync --extra dev`): 230 passed, 7 skipped, 0 failed. The skips need optional packages that are not installed by default (`onnxruntime`, `onnxmltools`) or fail to import `google.cloud.bigquery` (`pkg_resources` missing in this environment). The CI workflow is `.github/workflows/ci.yml`.

The tests read and write `~/.lewagon/mlops/training_outputs`. If a model from an earlier training run is saved there, two tests in `tests/api/test_routers.py` that expect "no model loaded" fail; run them with `REGISTRY_LOCAL_PATH=$(mktemp -d)` to isolate.

## Extending

- **Backend**: subclass `AbstractEstimator` in `deepCab/models/`, add a `*Config` with `kind: Literal[...]` to `deepCab/schemas/config.py` (and `BACKEND_CONFIGS`), register it in `deepCab/models/_kinds.py::BACKENDS`. ONNX export goes in `deepCab/models/onnx_export.py`.
- **Agent tool**: add `(InputModel, fn, "description")` to `_TOOLS` in `deepCab/agent/tools.py`.
- **Endpoint**: add a router under `deepCab/api/routers/` and include it in `deepCab/api/app.py::create_app`.

## Known issues

These are documented, not fixed, in this pass:

- `deepCab.data.migrate` overwrites `part-0.parquet` when `train` and `val` of the same size are migrated one after the other, so the first split is lost (`make bootstrap` runs exactly that sequence). Workaround above.
- `POST /explain` and `GET /explain/summary` raised `ValueError: could not convert string to float` for an XGBoost model with the pinned `shap 0.49.1` and `xgboost 3.2.0`; they worked for LightGBM.
- Several Makefile targets are stale: `test_api` has no recipe, `default` and `list` mention the old `taxifare` package, `run_train`/`run_api`/`bootstrap` call bare `python`/`uvicorn` (activate `.venv` first or use `uv run`).

## More

- `notebooks/README.md`: lesson notebooks (00, 02 and 07 are full lessons, the rest are scaffolds).
- `CONTRIBUTING.md`: setup, test loop and a runbook for common errors.
- `infra/AUDIT.md`: earlier simplification pass (complexity and dead-code numbers, with raw output in `infra/audit/`).
- `docs/superpowers/`: design plans per sub-project.

Deferred, as listed in the previous README: multi-worker serving with shared state, drift detection, per-user rate limiting, an LLM-driven `propose_next_experiment`.
