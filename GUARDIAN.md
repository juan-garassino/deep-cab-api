# GUARDIAN

Security & bug-fix ledger maintained by the Guardian agent. Work lands only on
the `claude/guardian` branch via a single draft PR into `main`.

## Checks

| Area | Tool / rule |
|---|---|
| Dependency vulns | `pip-audit` over `uv export --frozen --all-extras` (no-deps mode, OSV/PyPI advisories) |
| Risky code | `bandit -r deepCab`; grep for `eval`/`exec`, `pickle`/`torch.load` (checked `weights_only=True`), `yaml.load`, `shell=True`, SQL via f-strings, `verify=False`, CORS `*`, `0.0.0.0` binds |
| Secrets | regexes (cloud/API/chat/Git tokens, private keys, Slack webhooks, Telegram bot tokens) over the working tree AND `git log -p --all`; scan of every `.env`-like file ever committed |
| GitHub Actions | actions pinned by SHA, top-level `permissions`, `${{ }}` expressions inside `run:` |
| Dockerfiles | non-root `USER`, base image pinning |
| Tests / lint | `pytest tests/ --ignore=tests/all`, `ruff check`, `ruff format --check`, `mypy deepCab --ignore-missing-imports --check-untyped-defs` (informational in CI) |

Severity for dependency advisories is assigned per package by exposure
(network-facing / model-loading = high, transitive server libs = medium,
dev/docs-only = low), since pip-audit does not report CVSS.

## Findings ledger

| id | severity | type | file | status | date |
|---|---|---|---|---|---|
| G-001 | critical | secret | URGENT: possible credential exposure, see the owner's private run summary | open (owner action) | 2026-10-15 |
| G-002 | high | dep-vuln | uv.lock: starlette, python-multipart, cryptography | fixed (patch bumps) | 2026-10-15 |
| G-003 | high | dep-vuln | uv.lock: mlflow 2.22.5 (pinned `<3`), torch 2.5.1 (pinned `<2.6`), keras 3.14.1 / onnx 1.19.0, strawberry-graphql 0.315.5 | open (needs major bumps, see Backlog) | 2026-10-15 |
| G-004 | medium | docker | infra/docker/Dockerfile (runtime ran as root) | fixed | 2026-10-15 |
| G-005 | medium | ci | .github/workflows/ci.yml, train-smoke.yml (no `permissions:` = default token scope) | open (patch in PR; agent token lacks `workflow` scope) | 2026-10-15 |
| G-006 | low | ci | deploy-*.yml: `workflow_dispatch` inputs interpolated into `run:` | open (patch in PR: pass via `env:`) | 2026-10-15 |
| G-007 | medium | bug/DoS | deepCab/api/middleware.py: 404 paths became Prometheus label values (unbounded cardinality) | fixed | 2026-10-15 |
| G-008 | low | input | deepCab/api/middleware.py: client `X-Request-Id` echoed/logged unbounded | fixed | 2026-10-15 |
| G-009 | medium | ci | all workflows: actions referenced by mutable tags (incl. 3rd-party action receiving a secret) | open (patch in PR: SHA pins) | 2026-10-15 |
| G-010 | medium | dep-vuln | uv.lock: urllib3, pydantic-settings, anyio, h2, hpack, werkzeug, pillow, tornado, gitpython, jupyter-server, pyasn1 | fixed (patch/minor bumps) | 2026-10-15 |
| G-011 | medium | dep-vuln | uv.lock: prefect 3.5.0, pyarrow 19.0.1, protobuf 4.25.9 (held by tensorflow<2.17); hydra-core fixed 1.3.6 -> 1.3.7 (run 2) | partial | 2026-10-17 |
| G-012 | low | dep-vuln | uv.lock: fsspec, sqlparse, soupsieve, apprise, bleach (fixed); mistune (fixed 3.3.4, run 2); oauthlib, setuptools, uv (open) | partial | 2026-10-15 |
| G-013 | low | code | deepCab/data/bigquery.py: SQL built from f-strings (callers are internal/trusted) | wontfix (documented trusted fragments) | 2026-10-15 |
| G-014 | low | code | deepCab/cli/serve.py: default bind 0.0.0.0 | wontfix (container entrypoint) | 2026-10-15 |
| G-015 | low | docker | infra/docker/Dockerfile: `python:3.11-slim` not digest-pinned | open | 2026-10-15 |
| G-016 | medium | auth | deepCab/api/deps.py: `api_key_guard` failed OPEN when no key set, incl. `APP_ENV=prod` (Cloud Run manifest sets no `DEEPCAB_API_KEY`) -> unauthenticated /train, /agent, /graphql; key compared with `!=` (timing) | fixed (503 in prod, `hmac.compare_digest`) | 2026-10-17 |
| G-017 | low | ci | build-and-push.yml: `inputs.tag` interpolated into `run:` (missed by run 1's G-006 patch) | open (added to workflow patch) | 2026-10-17 |

## Metrics

| Metric | Before (run 1) | After (run 1) | After (run 2) |
|---|---|---|---|
| Open findings crit / high / med / low | 1 / 8 / 19 / 14 | 1 / 5 / 6 / 8 | 1 / 5 / 5 / 8 |
| Vulnerable packages (pip-audit) | 32 | 13 | 11 |
| Unique advisories (pip-audit) | 173 | 78 | 76 |
| Failing tests | 0 | 0 | 0 (full env); run 2 used a light venv, see Log |
| Tests passed / skipped | 230 / 7 | 233 / 7 | light venv: 183 -> 185 passed / 30 skipped (7 env-only import errors, identical before/after) |
| ruff check errors | 0 | 0 | 0 |
| ruff format diffs | 0 | 0 | 0 |
| mypy errors (informational) | 73 | 73 | not re-run |
| bandit (high / med / low) | 0 / 2 / 10 | 0 / 2 / 10 | 0 / 2 / 10 |

Coverage not measured (pytest-cov not in the dev extra).

## Backlog

1. **mlflow 3.x migration** (largest remaining advisory cluster, 27 advisories). Needs `mlflow>=3.15` and an audit of `deepCab/obs/mlflow.py` / registry promotion against the 3.x client API.
2. **torch >= 2.6 / tensorflow >= 2.17** to clear torch, keras and protobuf advisories; currently capped in `pyproject.toml`. `torch.load` already uses `weights_only=True`, which mitigates the most severe torch advisory class.
3. **strawberry-graphql >= 0.327.2**: lock carries two forked versions; resolving to one needs `uv lock` with the newer uv lock revision, which would rewrite the entire lockfile. Upgrade the Dockerfile's pinned `uv` (0.6.8) together with the lock revision in one PR, then bump strawberry, prefect and pyarrow.

Ideas (run 2): a CI test that boots `create_app()` with `APP_ENV=prod` and asserts every mutating route is gated; a cached CPU-only `uv sync` (torch CPU index) so Guardian runs can execute the full suite in budget; grep-check in CI for `${{ inputs.` inside `run:` blocks.

Ideas (run 1): add `pip-audit` + `bandit` as a non-blocking CI job; add `pytest-cov` to the dev extra so coverage can be tracked here; pin base images by digest with Dependabot/Renovate updating them.

## Learnings

- Running `uv lock --upgrade-package` with a recent uv rewrites ~4k lines of `uv.lock` (revision 1 -> 3, adds `upload-time`). To keep diffs reviewable and stay readable by the uv 0.6.8 used in the Dockerfile, only the upgraded `[[package]]` blocks were spliced in, then validated with `uv lock --check` and a full `uv sync --frozen` + test run.
- The agent's push token cannot modify `.github/workflows/*` (no `workflow` scope): CI fixes must be delivered as patches for the owner.
- Run 2: the full `uv sync --frozen --extra dev` pulls CUDA wheels and did not finish in 10 min; a light venv (fastapi/pydantic/strawberry/xgboost/pyarrow...) runs ~95% of the suite in seconds. Compare before/after on the same venv.
- Run 2: the workflow push was refused again (no `workflow` scope) — stop retrying unless the owner says the token changed.
- A full `uv sync --extra dev` (torch + tensorflow + CUDA wheels) takes ~12 minutes here; budget for it.

## Log

- Run 1 — 2026-10-15 — Branch created, pre-push guard installed. Scanned deps (pip-audit), code (bandit + greps), secrets (tree + full history), workflows and Dockerfile. Fixed: patch/minor bumps clearing 19 vulnerable packages (32 -> 13 vulnerable), non-root container user, Prometheus route-label cardinality bug and request-id sanitization (3 new tests, written failing first). URGENT: possible credential exposure, see the owner's private run summary. Workflow hardening (G-005/G-006/G-009) was prepared but could not be pushed: the agent's token lacks the `workflow` scope; the patch is in the PR description for the owner to apply.
- Run 2 — 2026-10-17 — No PR review comments; main had no new commits. Workflow-hardening push retried once, refused again (no `workflow` scope); patch refreshed in PR body and extended with G-017. Fixed G-016 (api_key_guard fail-open in prod + timing-unsafe compare; 2 tests written failing first). Spliced hydra-core 1.3.7 and mistune 3.3.4 into uv.lock (`uv lock --check` OK); pip-audit 13 -> 11 vulnerable packages. Tests run in a light venv (full CUDA sync too slow). Secret regexes over the tree: only placeholder matches; G-001 still awaiting owner action.
