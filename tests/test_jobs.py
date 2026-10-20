"""Background job runner, driven synchronously in tests."""
import threading

from kumquat.jobs import Job
from kumquat.progress import Progress


def _sync_post(fn, *args):
    fn(*args)


def test_job_reports_progress_then_result():
    seen, done = [], []

    def work(progress):
        progress(Progress(0.5))
        return "out.png"

    job = Job(work, on_progress=seen.append, on_done=lambda r, e: done.append((r, e)),
              post=_sync_post)
    job.start()
    job.join(timeout=5)
    assert [p.fraction for p in seen] == [0.5]
    assert done == [("out.png", None)]


def test_job_reports_exception_instead_of_dying_silently():
    done = []

    def work(_progress):
        raise RuntimeError("boom")

    job = Job(work, on_progress=lambda p: None,
              on_done=lambda r, e: done.append((r, e)), post=_sync_post)
    job.start()
    job.join(timeout=5)
    assert done[0][0] is None
    assert isinstance(done[0][1], RuntimeError)


def test_job_runs_off_the_calling_thread():
    caller = threading.get_ident()
    worker = []
    job = Job(lambda _p: worker.append(threading.get_ident()),
              on_progress=lambda p: None, on_done=lambda r, e: None, post=_sync_post)
    job.start()
    job.join(timeout=5)
    assert worker and worker[0] != caller


def test_running_flag():
    gate = threading.Event()
    job = Job(lambda _p: gate.wait(5), on_progress=lambda p: None,
              on_done=lambda r, e: None, post=_sync_post)
    job.start()
    assert job.running
    gate.set()
    job.join(timeout=5)
    assert not job.running
