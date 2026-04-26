from __future__ import annotations

import subprocess
import sys
from pathlib import Path


EXAMPLE_SCRIPTS = [
    "tool_call_match_example.py",
    "regex_match_example.py",
    "semantic_match_example.py",
    "tool_call_variables_example.py",
    "tool_call_semantic_args_example.py",
]


def test_example_scripts_run_successfully() -> None:
    root = Path(__file__).resolve().parents[1]
    examples_dir = root / "examples"

    for script_name in EXAMPLE_SCRIPTS:
        completed = subprocess.run(
            [sys.executable, str(examples_dir / script_name)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "PASS" in completed.stdout
