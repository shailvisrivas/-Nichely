"""
Phase 14 test — live/production readiness check.

Verifies check_live_readiness() correctly reports missing vs. complete
setup, without needing real credentials.

Run with:
    python -m tests.test_phase14_live_readiness
"""

import os
from unittest.mock import patch

import pipeline


def run():
    print("Starting Phase 14 live-readiness test...")

    # -----------------------------------------------------
    # Test 1: nothing configured -> not ready, all issues listed
    # -----------------------------------------------------
    print("\nTesting with no credentials set...")
    env_vars = ["IG_APP_ID", "IG_APP_SECRET", "IG_ACCESS_TOKEN", "IG_USER_ID", "CLOUDINARY_URL"]
    with patch.dict(os.environ, {var: "" for var in env_vars}, clear=False):
        for var in env_vars:
            os.environ.pop(var, None)
        result = pipeline.check_live_readiness()
        assert result["ready"] is False
        assert len(result["issues"]) == 5
        print(f"  Correctly reported {len(result['issues'])} issues.")

    # -----------------------------------------------------
    # Test 2: everything configured -> ready
    # -----------------------------------------------------
    print("\nTesting with all credentials set...")
    fake_env = {
        "IG_APP_ID": "1",
        "IG_APP_SECRET": "2",
        "IG_ACCESS_TOKEN": "3",
        "IG_USER_ID": "4",
        "CLOUDINARY_URL": "cloudinary://key:secret@cloud",
    }
    with patch.dict(os.environ, fake_env, clear=False):
        result = pipeline.check_live_readiness()
        assert result["ready"] is True
        assert result["issues"] == []
        print("  Correctly reported ready=True.")

    print("\nPhase 14 live-readiness test completed successfully.")


if __name__ == "__main__":
    run()
