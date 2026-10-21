import pytest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    sys.path.insert(0, str(path.parent))
    spec = spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_start_uses_script_entrypoint_for_enricher() -> None:
    module = _load_module("start_script", "scripts/start.py")

    _, args, _ = module.ALL_SERVICES["enricher"]

    assert args == ["scripts/enricher.py"]


def test_stop_matches_both_canonical_and_legacy_enricher_processes() -> None:
    module = _load_module("stop_script", "scripts/stop.py")

    _, keywords = module.SERVICES["enricher"]

    assert "-m jobtracker.cli run enricher" in keywords
    assert "scripts/enricher.py" in keywords


def test_status_lists_canonical_and_legacy_enricher_processes() -> None:
    module = _load_module("status_script", "scripts/status.py")

    assert "-m jobtracker.cli run enricher" in module.PROCESS_KEYWORDS
    assert "scripts/enricher.py" in module.PROCESS_KEYWORDS


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process helpers")
def test_get_processes_parses_single_json_object(monkeypatch) -> None:
    module = _load_module("process_helpers_script", "scripts/process_helpers.py")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout='{"ProcessId":24148,"Name":"python.exe","CommandLine":"C:\\\\Python\\\\python.exe scripts/enricher.py"}'
        ),
    )

    processes = module.get_processes(("scripts/enricher.py",))

    assert processes == [
        {
            "ProcessId": 24148,
            "Name": "python.exe",
            "CommandLine": "C:\\Python\\python.exe scripts/enricher.py",
        }
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process helpers")
def test_get_processes_parses_json_array(monkeypatch) -> None:
    module = _load_module("process_helpers_script_array", "scripts/process_helpers.py")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                '[{"ProcessId":1,"Name":"python.exe","CommandLine":"a"},'
                '{"ProcessId":2,"Name":"python.exe","CommandLine":"b"}]'
            )
        ),
    )

    processes = module.get_processes(("scripts/enricher.py",))

    assert [process["ProcessId"] for process in processes] == [1, 2]


def test_start_reports_already_running_when_count_is_nonzero(monkeypatch, capsys) -> None:
    module = _load_module("start_script_existing", "scripts/start.py")

    monkeypatch.setattr(module, "count_processes", lambda keywords: 1)
    monkeypatch.setattr(module, "_start", lambda args, log_stem: (_ for _ in ()).throw(AssertionError("should not start")))

    module._launch(module.SERVICES["enricher"])

    output = capsys.readouterr().out
    assert "ALREADY RUNNING" in output


def test_enricher_configures_multiprocessing_to_use_current_python(monkeypatch) -> None:
    module = _load_module("enricher_script", "scripts/enricher.py")
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(module.multiprocessing, "freeze_support", lambda: calls.append(("freeze_support", None)))
    monkeypatch.setattr(
        module.multiprocessing,
        "set_executable",
        lambda executable: calls.append(("set_executable", executable)),
    )
    monkeypatch.setattr(module.sys, "executable", r"C:\app\.venv\Scripts\python.exe")

    module._configure_multiprocessing()

    assert calls == [
        ("freeze_support", None),
        ("set_executable", r"C:\app\.venv\Scripts\python.exe"),
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process helpers")
def test_enricher_single_instance_returns_false_when_mutex_exists(monkeypatch) -> None:
    module = _load_module("enricher_script_mutex_exists", "scripts/enricher.py")
    close_calls: list[int] = []

    class Kernel32:
        def CreateMutexW(self, security, initial_owner, name):
            return 123

        def CloseHandle(self, handle):
            close_calls.append(handle)

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "windll", SimpleNamespace(kernel32=Kernel32()))
    monkeypatch.setattr(module.ctypes, "GetLastError", lambda: 183)

    assert module._acquire_single_instance() is False
    assert close_calls == [123]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only process helpers")
def test_enricher_single_instance_keeps_mutex_handle(monkeypatch) -> None:
    module = _load_module("enricher_script_mutex_new", "scripts/enricher.py")
    registered: list[object] = []

    class Kernel32:
        def CreateMutexW(self, security, initial_owner, name):
            return 456

        def CloseHandle(self, handle):
            raise AssertionError("should not close handle during acquire")

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "windll", SimpleNamespace(kernel32=Kernel32()))
    monkeypatch.setattr(module.ctypes, "GetLastError", lambda: 0)
    monkeypatch.setattr(module.atexit, "register", lambda fn: registered.append(fn))

    assert module._acquire_single_instance() is True
    assert module._mutex_handle == 456
    assert registered == [module._release_single_instance]


def test_ingestor_configures_multiprocessing_to_use_current_python(monkeypatch) -> None:
    module = _load_module("ingestor_script", "scripts/ingestor.py")
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(module.multiprocessing, "freeze_support", lambda: calls.append(("freeze_support", None)))
    monkeypatch.setattr(
        module.multiprocessing,
        "set_executable",
        lambda executable: calls.append(("set_executable", executable)),
    )
    monkeypatch.setattr(module.sys, "executable", r"C:\app\.venv\Scripts\python.exe")

    module._configure_multiprocessing()

    assert calls == [
        ("freeze_support", None),
        ("set_executable", r"C:\app\.venv\Scripts\python.exe"),
    ]
