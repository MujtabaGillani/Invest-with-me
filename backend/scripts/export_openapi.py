"""Write the OpenAPI schema to a file for the frontend's type generation.

Run from ``backend/``:

    python scripts/export_openapi.py

The frontend generates its TypeScript types from the emitted file rather than
from a running server, so ``npm run codegen`` works offline and in CI. The file
is committed, which makes any API contract change visible as a reviewable diff.

Re-run this whenever a schema or endpoint changes, then re-run codegen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Importable when invoked as a script from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Environment, Settings
from app.main import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent.parent / "frontend" / "openapi.json"


def export(output: Path = DEFAULT_OUTPUT) -> Path:
    """Generate the schema and write it as formatted JSON.

    Built with seeding and auto-migration disabled so that exporting a schema
    never touches a database.
    """
    settings = Settings(
        environment=Environment.LOCAL,
        auto_migrate=False,
        seed_on_startup=False,
        database_url="sqlite+pysqlite:///:memory:",
    )
    schema = create_app(settings).openapi()

    output.parent.mkdir(parents=True, exist_ok=True)
    # Sorted keys and a trailing newline keep the committed diff minimal and
    # stable between runs.
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    written = export(target)
    print(f"Wrote OpenAPI schema to {written}")
