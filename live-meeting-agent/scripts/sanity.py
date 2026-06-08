import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

for name, transcript in [
    ("sanity-arch", "tests/fixtures/transcript_architecture.txt"),
    ("sanity-process", "tests/fixtures/transcript_process.txt"),
]:
    print(f"\n=== {name} ===")
    subprocess.run([str(PYTHON), "agent.py", name, "--transcript", transcript], cwd=ROOT, check=True)
    print(f"-> meetings/{name}/meeting.drawio")
