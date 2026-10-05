import shutil
import subprocess
from pathlib import Path

import pytest

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-book"


@pytest.fixture
def sample(tmp_path) -> Path:
    """A writable copy of the sample book, as its own git repository."""

    root = tmp_path / "sample-book"
    shutil.copytree(SAMPLE, root, ignore=shutil.ignore_patterns("builds", "state.json"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], cwd=root,
                   check=True)
    return root
