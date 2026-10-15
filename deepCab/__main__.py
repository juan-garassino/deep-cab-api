"""`python -m deepCab ...` -> unified Typer CLI.

Mirrors the `[project.scripts] deepcab = "deepCab.cli:app"` binding so the
package is usable without an installed console script (handy in containers
that run via `python -m`).
"""

from __future__ import annotations

from deepCab.cli import app


def main() -> None:
    """Run the Typer CLI (same app as the `deepcab` console script)."""
    app()


if __name__ == "__main__":
    main()
