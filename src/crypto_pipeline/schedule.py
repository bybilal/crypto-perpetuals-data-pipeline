"""Install, inspect or stop the macOS user-level live collector."""
# The scheduler uses native plist generation and launchctl without a shell.
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from .config import PROJECT_ROOT

# A stable service label identifies only this project's collector.
LABEL = "com.crypto-pipeline.collector"


def launch_agent(root):
    """Build a portable configuration using the selected repository's virtual environment."""
    # Resolve the repository, while preserving the virtual-environment Python symlink.
    root = root.resolve()
    return {
        "Label": LABEL,
        "ProgramArguments": [str(root / ".venv/bin/python"), "-m", "crypto_pipeline",
                             "--human-log", "--limit", "25", "--coverage"],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {"CRYPTO_PIPELINE_ROOT": str(root), "PYTHONUNBUFFERED": "1"},
        # Run at minutes 01, 06, 11, etc., allowing a minute for publication after the boundary.
        "StartCalendarInterval": [{"Minute": minute} for minute in range(1, 60, 5)],
        # Run once at installation/login as well, recovering recent data after an interruption.
        "RunAtLoad": True,
        # Append plain terminal output so failures before JSONL initialization are still visible.
        "StandardOutPath": str(root / "logs/scheduler.stdout.log"),
        "StandardErrorPath": str(root / "logs/scheduler.stderr.log"),
    }


def main():
    # Keep installation an explicit operation rather than an import side effect.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "stop"))
    args = parser.parse_args()
    # This local deployment uses macOS's per-user scheduler.
    if sys.platform != "darwin":
        parser.error("This schedule requires macOS launchd")
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    path = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if args.action == "status":
        # Return launchctl's real status instead of claiming a service is running.
        return subprocess.run(["/bin/launchctl", "print", service]).returncode
    if args.action == "stop":
        # Unload the service while keeping the plist available for a later reinstallation.
        return subprocess.run(["/bin/launchctl", "bootout", service]).returncode
    # Refuse installation if the environment has not been created at the documented location.
    if not (PROJECT_ROOT / ".venv/bin/python").exists():
        parser.error("Create .venv and install the package before installing the schedule")
    spec = launch_agent(PROJECT_ROOT)
    # Refuse to overwrite a different configuration that happens to share our label.
    if path.exists() and plistlib.loads(path.read_bytes()) != spec:
        parser.error(f"Existing configuration differs; review {path} before replacing it")
    # Repeated installation of the same active service is a successful no-op.
    status = subprocess.run(["/bin/launchctl", "print", service], capture_output=True)
    if status.returncode == 0:
        print(f"Already loaded: {service}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    # Serialize valid XML with proper escaping for paths containing spaces or special characters.
    if not path.exists():
        with path.open("xb") as output:
            plistlib.dump(spec, output)
    # A failed bootstrap remains visible through the command's nonzero exit code.
    result = subprocess.run(["/bin/launchctl", "bootstrap", domain, str(path)])
    if result.returncode == 0:
        print(f"Loaded {service}; collection runs every five minutes while logged in.")
    return result.returncode


# Run only when explicitly invoked as python -m crypto_pipeline.schedule.
if __name__ == "__main__":
    raise SystemExit(main())
