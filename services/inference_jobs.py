"""Bounded in-process executor for background inference jobs.

This is the "no new infrastructure" async path: a single ThreadPoolExecutor per
process runs the slow model inference off the request thread. There is no broker
and no separate worker process, so it fits the default single-container
deployment. The tradeoff versus Celery/RQ: jobs live in this process, so an
in-flight job is lost if the process is killed (the caller sees it stay
``running`` — the row is not falsely marked done).

The actual work function is supplied by the caller (``routes.inspections``) so
this module stays free of route/model imports and there is no import cycle.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def get_executor(app) -> ThreadPoolExecutor:
    """Return the process-wide executor, creating it on first use."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=app.config["INFERENCE_WORKERS"],
                    thread_name_prefix="atis-infer",
                )
    return _executor


def submit_job(app, job_id: str, runner: Callable[[object, str], None]) -> None:
    """Run ``runner(app, job_id)`` on the pool, or inline in sync-jobs mode.

    ``app`` must be the real application object (not the ``current_app`` proxy),
    since the runner executes in another thread and pushes its own app context.
    """
    if app.config["INFERENCE_SYNC_JOBS"]:
        runner(app, job_id)
        return
    get_executor(app).submit(runner, app, job_id)


def shutdown() -> None:
    """Tear down the executor (used by tests)."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None
