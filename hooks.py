import shutil
import subprocess
import sys
from pathlib import Path

REVISION = "fecb9a1e3cc23ef84de30b272059457a427f16f8"
SOURCE = "https://github.com/OpenMontageInc/OpenMontage.git"
ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "_runtime"
SOURCE_DIR = RUNTIME / "OpenMontage"
PYTHON = Path(sys.executable)


def install(**kwargs):
    dependencies = subprocess.run([str(PYTHON), "-c", "import yaml, jsonschema, pydantic, PIL, numpy, requests, dotenv"], capture_output=True, timeout=30)
    if dependencies.returncode:
        raise RuntimeError("OpenMontage requires A0's PyYAML, jsonschema, Pydantic, Pillow, NumPy, requests and python-dotenv packages in the framework environment.")
    for executable in ("git", "ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            raise RuntimeError(f"OpenMontage requires {executable} in the Agent Zero server runtime.")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    marker = SOURCE_DIR / ".a0-revision"
    if not marker.is_file() or marker.read_text() != REVISION:
        staging = RUNTIME / "source-install"
        if staging.exists():
            shutil.rmtree(staging)
        try:
            for command in (
                ["git", "init", str(staging)],
                ["git", "-C", str(staging), "remote", "add", "origin", SOURCE],
                ["git", "-C", str(staging), "fetch", "--depth=1", "origin", REVISION],
                ["git", "-C", str(staging), "checkout", "--detach", "FETCH_HEAD"],
            ):
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
            if not (staging / "lib" / "checkpoint.py").is_file():
                raise RuntimeError("OpenMontage checkout is incomplete.")
            shutil.rmtree(staging / ".git")
            (staging / ".a0-revision").write_text(REVISION)
            if SOURCE_DIR.exists():
                shutil.rmtree(SOURCE_DIR)
            staging.rename(SOURCE_DIR)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    subprocess.run([str(PYTHON), "-c", "from lib.checkpoint import init_project; from tools.tool_registry import registry"], cwd=SOURCE_DIR, check=True, timeout=60)


def uninstall(**kwargs):
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
