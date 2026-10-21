from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
VENV_SCRIPTS = str(ROOT / ".venv" / "Scripts")

POWERSHELL = ["powershell", "-NoProfile", "-Command"]
PROCESS_EXCLUDES = ("powershell.exe", "bash.exe")


@dataclass(frozen=True)
class ServiceSpec:
    label: str
    args: tuple[str, ...]
    keywords: tuple[str, ...]
    log_stem: str


SERVICES: dict[str, ServiceSpec] = {
    "ingestor": ServiceSpec(
        label="ingestor",
        args=("scripts/ingestor.py",),
        keywords=("-m jobtracker.cli run ingestor", "scripts/ingestor.py"),
        log_stem="ingestor",
    ),
    "enricher": ServiceSpec(
        label="enricher",
        args=("scripts/enricher.py",),
        keywords=("-m jobtracker.cli run enricher", "scripts/enricher.py"),
        log_stem="enricher",
    ),
    "web": ServiceSpec(
        label="web",
        args=("scripts/web.py",),
        keywords=("-m jobtracker.cli web", "scripts/web.py"),
        log_stem="web",
    ),
}

PROCESS_KEYWORDS = tuple(
    keyword
    for spec in SERVICES.values()
    for keyword in spec.keywords
)


def build_child_env(environ: dict[str, str]) -> dict[str, str]:
    return {
        **environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PATH": f"{VENV_SCRIPTS};{environ.get('PATH', '')}",
        "VIRTUAL_ENV": str(ROOT / ".venv"),
    }


def _escape_single_quotes(value: str) -> str:
    return value.replace("'", "''")


def _keyword_clauses(keywords: tuple[str, ...]) -> str:
    return " -or ".join(
        f"$_.CommandLine -like '*{_escape_single_quotes(keyword)}*'"
        for keyword in keywords
    )


def process_query(keywords: tuple[str, ...]) -> str:
    exclusions = " -and ".join(
        f"$_.Name -ne '{name}'"
        for name in PROCESS_EXCLUDES
    )
    return (
        "Get-WmiObject Win32_Process "
        f"| Where-Object {{ ({_keyword_clauses(keywords)}) -and {exclusions} }}"
    )


def _run_ps_json(script: str) -> object:
    result = subprocess.run(
        [*POWERSHELL, script],
        capture_output=True,
        text=True,
    )
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _is_venv_stub(proc: dict[str, str]) -> bool:
    """UV venvs on Windows use a launcher stub that spawns the base interpreter as a child.
    A single logical service therefore surfaces as (stub, child). We treat the stub — the
    process whose ExecutablePath lives under the venv — as the canonical process.
    """
    path = (proc.get("ExecutablePath") or "").lower()
    return path.startswith(VENV_SCRIPTS.lower())


def get_processes(keywords: tuple[str, ...]) -> list[dict[str, str]]:
    parsed = _run_ps_json(
        f"{process_query(keywords)} "
        "| Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine "
        "| ConvertTo-Json -Compress"
    )
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        items = [parsed]
    elif isinstance(parsed, list):
        items = [item for item in parsed if isinstance(item, dict)]
    else:
        return []
    return [item for item in items if _is_venv_stub(item)]


def count_processes(keywords: tuple[str, ...]) -> int:
    return len(get_processes(keywords))


def _get_child_pids(parent_pid: int) -> list[int]:
    parsed = _run_ps_json(
        f"Get-WmiObject Win32_Process | Where-Object {{ $_.ParentProcessId -eq {parent_pid} }} "
        "| Select-Object ProcessId | ConvertTo-Json -Compress"
    )
    if parsed is None:
        return []
    items = parsed if isinstance(parsed, list) else [parsed]
    pids: list[int] = []
    for item in items:
        if isinstance(item, dict) and "ProcessId" in item:
            try:
                pids.append(int(item["ProcessId"]))
            except (TypeError, ValueError):
                continue
    return pids


def stop_process(process_id: int) -> None:
    """Stop a stub process along with any children it spawned (e.g. the uv venv
    redirector keeps the real interpreter alive as a child)."""
    for child_pid in _get_child_pids(process_id):
        subprocess.run(
            [*POWERSHELL, f"Stop-Process -Id {child_pid} -Force"],
            capture_output=True,
            text=True,
        )
    subprocess.run(
        [*POWERSHELL, f"Stop-Process -Id {process_id} -Force"],
        capture_output=True,
        text=True,
    )
