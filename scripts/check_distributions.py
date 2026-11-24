"""Install each built distribution and audit a public fixture outside the checkout."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    for pattern in ("*.whl", "*.tar.gz"):
        artifacts = list((root / "dist").glob(pattern))
        if len(artifacts) != 1:
            raise SystemExit(f"Expected exactly one {pattern} in dist, found {len(artifacts)}")
        with tempfile.TemporaryDirectory(prefix="auditor-package-") as directory:
            workspace = Path(directory)
            venv.create(workspace / "venv", with_pip=True)
            bin_dir = workspace / "venv" / ("Scripts" if os.name == "nt" else "bin")
            suffix = ".exe" if os.name == "nt" else ""
            python = str(bin_dir / ("python" + suffix))
            cli = str(bin_dir / ("local-llm-code-auditor" + suffix))
            for command in (
                [python, "-I", "-m", "pip", "install", "--no-deps", str(artifacts[0])],
                [cli, "--help"],
                [python, "-I", str(root / "scripts" / "demo.py")],
            ):
                result = subprocess.run(
                    command, cwd=workspace, env=environment, capture_output=True
                )
                if result.returncode:
                    sys.stderr.buffer.write(result.stdout + result.stderr)
                    raise SystemExit(result.returncode)
        print(f"Installed {artifacts[0].name} and passed the deterministic demo.")


if __name__ == "__main__":
    main()
