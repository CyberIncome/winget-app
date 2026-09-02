from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_job_uses_kill_on_close_and_assignment():
    source = (ROOT / "src" / "logic" / "windows_job.py").read_text(encoding="utf-8")
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000" in source
    assert "SetInformationJobObject" in source
    assert "AssignProcessToJobObject" in source
    assert "CloseHandle" in source


def test_managed_winget_workers_require_tree_containment():
    version_workers = (ROOT / "src" / "logic" / "version_workers.py").read_text(
        encoding="utf-8"
    )
    worker_jobs = (ROOT / "src" / "logic" / "worker_jobs.py").read_text(
        encoding="utf-8"
    )
    assert version_workers.count("require_process_tree_containment=True") >= 2
    assert "require_process_tree_containment=True" in worker_jobs
