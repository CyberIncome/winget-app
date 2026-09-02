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
    attach = "WindowsKillOnCloseJob.attach_current_process()"
    invoke = "target(*args, result_queue)"
    assert "def _managed_process_entry" in source
    assert attach in source
    assert invoke in source
    assert source.index(attach) < source.index(invoke)
    assert "target=_managed_process_entry" in source
    assert "_WORKER_CONTAINMENT_JOB" in source


def test_managed_winget_commands_inherit_worker_tree_without_nested_jobs():
    version_workers = (ROOT / "src" / "logic" / "version_workers.py").read_text(
        encoding="utf-8"
    )
    worker_jobs = (ROOT / "src" / "logic" / "worker_jobs.py").read_text(
        encoding="utf-8"
    )
    assert "run_command(" in version_workers
    assert "run_command(" in worker_jobs
    assert "require_process_tree_containment=True" not in version_workers
    assert "require_process_tree_containment=True" not in worker_jobs
