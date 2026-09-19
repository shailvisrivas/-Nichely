"""
Scheduler Service — Phase 12.

Provides a simple scheduling mechanism for the Nichely pipeline.

The scheduler can:
- Run a supplied function immediately.
- Run a supplied function repeatedly at a fixed interval.
- Run a supplied function once after a delay.

This first implementation uses only Python's standard library,
so no additional package is required.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional


class SchedulerError(RuntimeError):
    """Raised when a scheduling operation fails."""


class NichelyScheduler:
    """
    Simple scheduler for running Nichely pipeline jobs.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        """Return whether the scheduler is currently running."""

        return self._running

    def run_once(
        self,
        job: Callable[[], None],
        delay_seconds: float = 0,
    ) -> None:
        """
        Run a job once.

        If delay_seconds is greater than zero, the job waits
        for that many seconds before running.
        """

        if not callable(job):
            raise SchedulerError(
                "The scheduled job must be callable."
            )

        if delay_seconds < 0:
            raise SchedulerError(
                "delay_seconds cannot be negative."
            )

        if delay_seconds > 0:
            time.sleep(delay_seconds)

        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
            "Running scheduled Nichely job..."
        )

        job()

        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
            "Scheduled Nichely job completed."
        )

    def start_interval(
        self,
        job: Callable[[], None],
        interval_seconds: float,
        run_immediately: bool = False,
    ) -> None:
        """
        Run a job repeatedly at a fixed interval.

        Parameters:
            job:
                Function to execute.

            interval_seconds:
                Number of seconds between executions.

            run_immediately:
                If True, execute the job immediately before
                waiting for the first interval.
        """

        if not callable(job):
            raise SchedulerError(
                "The scheduled job must be callable."
            )

        if interval_seconds <= 0:
            raise SchedulerError(
                "interval_seconds must be greater than zero."
            )

        if self._running:
            raise SchedulerError(
                "Scheduler is already running."
            )

        self._stop_event.clear()
        self._running = True

        def scheduler_loop() -> None:
            try:
                if run_immediately:
                    self._execute_job(job)

                while not self._stop_event.wait(
                    interval_seconds
                ):
                    self._execute_job(job)

            finally:
                self._running = False

        self._thread = threading.Thread(
            target=scheduler_loop,
            daemon=True,
        )

        self._thread.start()

        print(
            f"Scheduler started. "
            f"Interval: {interval_seconds} seconds."
        )

    def _execute_job(
        self,
        job: Callable[[], None],
    ) -> None:
        """Execute one scheduled job safely."""

        try:
            print(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                "Starting Nichely pipeline job..."
            )

            job()

            print(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                "Nichely pipeline job completed."
            )

        except Exception as exc:
            # A failed job should not kill the scheduler.
            print(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                f"Scheduled job failed: {exc}"
            )

    def stop(self) -> None:
        """Stop the scheduler."""

        if not self._running:
            print("Scheduler is not running.")
            return

        print("Stopping Nichely scheduler...")

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(
                timeout=5
            )

        self._running = False

        print("Nichely scheduler stopped.")


def create_scheduler() -> NichelyScheduler:
    """Create and return a new Nichely scheduler."""

    return NichelyScheduler()


if __name__ == "__main__":

    print("=" * 60)
    print("PHASE 12 — SCHEDULER SERVICE")
    print("=" * 60)

    scheduler = create_scheduler()

    def demo_job() -> None:
        print("Demo Nichely job executed successfully.")


    print("\nRunning a one-time job...")

    scheduler.run_once(
        demo_job
    )

    print("\nStarting interval scheduler...")

    scheduler.start_interval(
        demo_job,
        interval_seconds=5,
        run_immediately=True,
    )

    try:
        time.sleep(12)

    finally:
        scheduler.stop()

    print("\nPhase 12 scheduler test completed.")