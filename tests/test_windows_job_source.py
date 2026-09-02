from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_job_uses_kill_on_close_and_assignment():
    source = (ROOT / "src" / "logic" / "windows_job.py").read_text(encoding="utf-8")
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000" in source
    assert "SetInformationJobObject" in source
    assert "AssignProcessToJobObject" in source
    assert "GetCurrentProcess" in source
    assert "attach_current_process" in source
    assert "CloseHandle" in source


def test_managed_worker_enters_containment_before_target_execution():
    source = (ROOT / "src" / "ui" / "process_jobs.py").read_text(encoding="utf-8")
    assert "def _managed_process_entry" in source
    assert "WindowsKillOnCloseJob.attach_current_process()" in source
    assert "target(*args, result_queue)" in source
    assert source.index("WindowsKillOnCloseJob.attach_current_process()") < source.index(
        "target(*args, result_queue)"
    )
    assert "target=_managed_process_entry" in source


def test_managed_winget_workers_also_require_command_level_containment():
    version_workers = (ROOT / "src" / "logic" / "version_workers.py").read_text(
        encoding="utf-8"
    )
    worker_jobs = (ROOT / "src" / "logic" / "worker_jobs.py").read_text(
        encoding="utf-8"
    )
    assert version_workers.count("require_process_tree_containment=True") >= 2
    assert worker_jobs.count("require_process_tree_containment=True") >= 2
