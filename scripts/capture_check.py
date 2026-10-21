"""Diagnostic tool to verify multi-monitor screen capture, mixed DPI, and negative coordinates.

Captures all connected monitors, prints detailed metrics, and saves the resulting
PNG snapshots to a temporary directory for visual inspection.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

# Ensure project root is in sys.path when script is executed directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from capture.screen_capture import ScreenCaptureManager


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    temp_dir = Path(tempfile.gettempdir()) / "Peachy" / "capture_check"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("PEACHY MULTI-MONITOR SCREEN CAPTURE DIAGNOSTIC")
    print("=" * 65)
    print(f"Output directory: {temp_dir}\n")

    manager = ScreenCaptureManager()
    captured_screens = manager.capture_all_screens()

    if not captured_screens:
        print("ERROR: No screens could be captured.")
        return 1

    print(f"Detected {len(captured_screens)} active display(s):\n")

    for idx, screen in enumerate(captured_screens):
        x, y, w, h = screen.logical_geom
        img_w = screen.pixmap.width()
        img_h = screen.pixmap.height()

        safe_name = screen.name.replace("\\", "_").replace(".", "").replace("/", "_")
        out_path = temp_dir / f"screen_{idx}_{safe_name}.png"
        screen.pixmap.save(str(out_path), "PNG")

        print(f"Display #{idx + 1}:")
        print(f"  Name:             {screen.name}")
        print(f"  Logical Geometry: x={x}, y={y}, width={w}, height={h}")
        print(f"  DevicePixelRatio: {screen.dpr:.2f}")
        print(f"  Physical Pixels:  {img_w} x {img_h}")
        print(f"  Capture Latency:  {screen.capture_time_ms:.2f} ms")
        print(f"  Saved Image:      {out_path}")
        print("-" * 65)

    print(f"\nAll snapshots successfully saved to: {temp_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
