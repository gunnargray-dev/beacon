#!/usr/bin/env python3
"""Beacon test runner -- runs tests in memory-safe batches via subprocess.

Usage: python run_tests.py [test_dir]

Why: The full test suite (677+ tests) exceeds memory limits when run in a single
pytest process. test_cli.py is especially heavy because each test spawns a
subprocess that imports the full beacon stack. This runner groups test files
into small batches, running each via subprocess to ensure cleanup between runs.

Exit code 0 = all passed, 1 = some failed.
"""
import gc
import os
import subprocess
import sys

# Each batch is run in a fresh subprocess. Keep batches small enough to avoid
# the sandbox per-command memory/timeout limits.
BATCHES = [
    ["test_advanced.py", "test_advanced_api.py", "test_advanced_core.py"],
    ["test_calendar_connector.py", "test_config.py", "test_connectors.py"],
    ["test_db_cli.py", "test_email_connector.py", "test_export_health_cli.py"],
    ["test_github_connector.py", "test_hackernews_connector.py"],
    ["test_health.py", "test_ingest.py", "test_intelligence.py"],
    ["test_models.py", "test_news_connector.py"],
    ["test_notifications.py", "test_ops.py"],
    ["test_store.py", "test_store_api.py", "test_store_export.py"],
    ["test_store_pagination.py", "test_store_query_pagination.py"],
    ["test_weather_connector.py"],
    ["test_web.py"],
    ["test_web_routes.py"],
    ["test_web_store_api.py", "test_web_store_stats_api.py"],
    # test_cli.py split into keyword batches (subprocess-per-test pattern is heavy)
]

# test_cli.py needs special handling -- split by keyword
CLI_KEYWORD_BATCHES = [
    "help or version or status or init",
    "sources",
    "sync",
]


def run_batch(test_dir, files, extra_args=None, timeout=90):
    """Run a batch of test files. Returns (ok: bool, summary: str)."""
    paths = [os.path.join(test_dir, f) for f in files if os.path.exists(os.path.join(test_dir, f))]
    if not paths:
        return True, "skipped (no files)"
    cmd = [sys.executable, "-m", "pytest"] + paths + ["-q", "--tb=short", "-p", "no:warnings", "--no-header"]
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        lines = result.stdout.strip().split("\n")
        summary = lines[-1].strip() if lines else ""
        return result.returncode == 0, summary
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"


def main():
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "tests"

    # Discover any new test files not in BATCHES
    known = {f for batch in BATCHES for f in batch}
    known.add("test_cli.py")  # handled separately
    all_files = sorted(f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py"))
    unknown = [f for f in all_files if f not in known]

    batches = list(BATCHES)
    if unknown:
        batches.append(unknown)

    passed = 0
    failed = 0
    failed_names = []
    batch_num = 0

    # Run regular batches
    for batch in batches:
        batch_num += 1
        label = ", ".join(batch)
        sys.stdout.write(f"  [{batch_num:2d}] {label:<60} ")
        sys.stdout.flush()
        ok, summary = run_batch(test_dir, batch)
        if ok:
            passed += 1
            sys.stdout.write(f"OK  ({summary})\n")
        else:
            failed += 1
            failed_names.extend(batch)
            sys.stdout.write(f"FAIL ({summary})\n")
        gc.collect()

    # Run test_cli.py in keyword splits
    for kw in CLI_KEYWORD_BATCHES:
        batch_num += 1
        sys.stdout.write(f"  [{batch_num:2d}] test_cli.py -k \"{kw}\"{'':>30} ")
        sys.stdout.flush()
        ok, summary = run_batch(test_dir, ["test_cli.py"], extra_args=["-k", kw])
        if ok:
            passed += 1
            sys.stdout.write(f"OK  ({summary})\n")
        else:
            failed += 1
            failed_names.append(f"test_cli.py ({kw})")
            sys.stdout.write(f"FAIL ({summary})\n")
        gc.collect()

    print()
    print("=" * 55)
    print(f"  Passed: {passed}  Failed: {failed}")
    print("=" * 55)
    if failed_names:
        print("Failed:")
        for n in failed_names:
            print(f"  - {n}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
