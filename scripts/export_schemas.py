"""Export JSON schemas for every public model to schemas/.

Run via ``make schemas``. Writes one file per model.
"""

from __future__ import annotations

import json
from pathlib import Path

from autogovern import models

SCHEMA_DIR = Path("schemas")


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name in models.__all__:
        model_cls = getattr(models, name)
        if not hasattr(model_cls, "model_json_schema"):
            continue
        schema = model_cls.model_json_schema()
        out = SCHEMA_DIR / f"{name}.json"
        out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
