"""Compatibility entry point for XSkill with its default Jina DNS override."""

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("infer_api.py")),
        run_name="__main__",
    )
