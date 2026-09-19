"""
Phase 12 Scheduler Test.

Run with:

    ..\venv\Scripts\python.exe -m tests.test_phase12_scheduler
"""

import time

from services.scheduler_service import (
    NichelyScheduler,
    SchedulerError,
    create_scheduler,
)


def run():

    print(
        "Starting Phase 12 Scheduler test..."
    )

    scheduler = create_scheduler()

    # --------------------------------------------------
    # Test 1: one-time job
    # --------------------------------------------------

    print(
        "\nTesting one-time scheduled job..."
    )

    results = []

    def test_job():
        results.append("executed")
        print(
            "Test job executed."
        )

    scheduler.run_once(
        test_job
    )

    if results != ["executed"]:
        raise AssertionError(
            "One-time job did not execute correctly."
        )

    print(
        "One-time job: SUCCESS"
    )

    # --------------------------------------------------
    # Test 2: interval scheduler
    # --------------------------------------------------

    print(
        "\nTesting interval scheduler..."
    )

    counter = []

    def interval_job():
        counter.append(
            time.time()
        )
        print(
            "Interval job executed."
        )

    scheduler.start_interval(
        interval_job,
        interval_seconds=2,
        run_immediately=True,
    )

    time.sleep(5)

    scheduler.stop()

    if len(counter) < 2:
        raise AssertionError(
            "Interval scheduler did not execute "
            "the job enough times."
        )

    print(
        f"Interval executions: {len(counter)}"
    )

    print(
        "Interval scheduler: SUCCESS"
    )

    # --------------------------------------------------
    # Test 3: validation
    # --------------------------------------------------

    print(
        "\nTesting scheduler validation..."
    )

    try:
        scheduler.start_interval(
            interval_job,
            interval_seconds=0,
        )

        raise AssertionError(
            "Invalid interval was not rejected."
        )

    except SchedulerError:
        print(
            "Invalid interval correctly rejected."
        )

    # --------------------------------------------------
    # Final result
    # --------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "PHASE 12 SCHEDULER TEST COMPLETED SUCCESSFULLY"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    run()