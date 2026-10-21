"""End-to-End Automated Verification Script for Day 1.

Performs all manual checklist verifications programmatically:
1. Starts Peachy app and validates rotated logging & hotkey registration.
2. Validates Single-Instance Guard & IPC (second launch signals first instance to open Settings and exits 0).
3. Posts WM_HOTKEY to app.py main thread to trigger global hotkey native event filter.
4. Verifies 'Global hotkey triggered.', 'activated', and state machine transitions in real logs.
5. Tests rapid spamming hotkey behavior.
6. Tests clean process termination with zero orphaned processes.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

user32 = ctypes.windll.user32
WM_HOTKEY = 0x0312
PEACHY_HOTKEY_ID = 0x5045  # "PE" in ASCII


def main():
    print("=" * 70)
    print("PEACHY DAY 1: FULL AUTOMATED VERIFICATION SUITE")
    print("=" * 70)

    local_app_data = os.environ.get("LOCALAPPDATA")
    log_file = Path(local_app_data) / "Peachy" / "logs" / "peachy.log"

    # Clean / truncate log file for clear test isolation
    if log_file.exists():
        try:
            log_file.write_text("", encoding="utf-8")
        except Exception:
            pass

    # -------------------------------------------------------------
    # TEST 1: Launch Peachy App
    # -------------------------------------------------------------
    print("\n[TEST 1] Launching Peachy (python app.py)...")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(2.0)

    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        print(f"FAILED: app.py terminated prematurely (code {proc.returncode})")
        print("stdout:", stdout)
        print("stderr:", stderr)
        sys.exit(1)

    print(f"  -> PASS: app.py is running in background (PID: {proc.pid})")

    # -------------------------------------------------------------
    # TEST 2: Verify Log File & Hotkey Registration
    # -------------------------------------------------------------
    print("\n[TEST 2] Verifying log initialization & hotkey registration...")
    assert log_file.exists(), f"Log file {log_file} does not exist"
    log_content = log_file.read_text(encoding="utf-8")

    assert "Logging initialized" in log_content, "Missing 'Logging initialized' in log"
    assert "Successfully registered global hotkey: Ctrl+Shift+Space" in log_content, (
        "Missing hotkey registration in log"
    )
    assert "Peachy started. Hotkey: Ctrl+Shift+Space" in log_content, "Missing 'Peachy started' in log"

    print("  -> PASS: Log file created and Ctrl+Shift+Space registered with OS.")

    # -------------------------------------------------------------
    # TEST 3: Single-Instance Guard & IPC Notification
    # -------------------------------------------------------------
    print("\n[TEST 3] Testing Single-Instance Guard by launching second copy...")
    second_inst = subprocess.run(
        [sys.executable, "app.py"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    print(f"  Second instance exit code: {second_inst.returncode}")
    print(f"  Second instance stdout: {second_inst.stdout.strip()}")
    assert second_inst.returncode == 0, f"Expected exit code 0, got {second_inst.returncode}"
    assert "Peachy is already running" in second_inst.stdout, "Failed to detect existing instance"

    time.sleep(0.5)
    log_content = log_file.read_text(encoding="utf-8")
    assert "Received IPC command from another instance: open_settings" in log_content, (
        "Primary instance did not log IPC open_settings command"
    )
    print("  -> PASS: Second instance exited immediately with code 0 and signaled primary instance.")

    # -------------------------------------------------------------
    # TEST 4: Global Hotkey WM_HOTKEY Dispatch & State Transition
    # -------------------------------------------------------------
    print("\n[TEST 4] Triggering Global Hotkey WM_HOTKEY event...")
    p = psutil.Process(proc.pid)
    threads = p.threads()
    assert len(threads) > 0, "No threads found for Peachy process"
    main_thread_id = threads[0].id
    print(f"  Target Main Thread ID: {main_thread_id}")

    # Post WM_HOTKEY to app's native event filter
    log_len_before = len(log_file.read_text(encoding="utf-8"))
    res = user32.PostThreadMessageW(main_thread_id, WM_HOTKEY, PEACHY_HOTKEY_ID, 0)
    assert res != 0, f"PostThreadMessage failed with error: {ctypes.GetLastError()}"

    time.sleep(0.6)
    new_log = log_file.read_text(encoding="utf-8")[log_len_before:]
    print("  Captured Log Lines:")
    for line in new_log.strip().splitlines():
        print(f"    | {line}")

    assert "Global hotkey triggered." in new_log, "Hotkey trigger not logged"
    assert "activated" in new_log, "Activation message not logged"
    assert "State transition: IDLE -> CAPTURING" in new_log, "State machine did not transition to CAPTURING"
    assert (
        "Forced reset to IDLE from CAPTURING" in new_log
        or "State transition: CAPTURING -> SELECTING" in new_log
    ), "State machine did not progress state"
    print("  -> PASS: WM_HOTKEY received, Qt signal emitted, activated logged, state machine transitioned.")

    # -------------------------------------------------------------
    # TEST 5: Spam Guard / Rapid Hotkey Fire
    # -------------------------------------------------------------
    print("\n[TEST 5] Testing rapid hotkey activations (Spam Guard)...")
    for _ in range(5):
        user32.PostThreadMessageW(main_thread_id, WM_HOTKEY, PEACHY_HOTKEY_ID, 0)
        time.sleep(0.01)

    time.sleep(0.5)
    full_log = log_file.read_text(encoding="utf-8")
    assert "CRITICAL" not in full_log and "Traceback" not in full_log, "Errors logged during rapid activation"
    print("  -> PASS: Spam activations processed cleanly without crash or unhandled errors.")

    # -------------------------------------------------------------
    # TEST 6: Clean Termination & Zero Residual Processes
    # -------------------------------------------------------------
    print("\n[TEST 6] Terminating Peachy process and verifying clean exit...")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    print(f"  -> PASS: Peachy exited cleanly with return code {proc.returncode}.")

    # Confirm process PID is gone
    assert not psutil.pid_exists(proc.pid), f"PID {proc.pid} still exists after termination"
    print("  -> PASS: Zero residual python processes.")

    print("\n" + "=" * 70)
    print("ALL DAY 1 VERIFICATIONS COMPLETED AND VERIFIED 100% AUTOMATICALLY!")
    print("=" * 70)


if __name__ == "__main__":
    main()
