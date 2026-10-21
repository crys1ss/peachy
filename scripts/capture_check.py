"""Verification script to test multi-monitor capture and DPI handling.

Usage:
    python scripts/capture_check.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtWidgets import QApplication

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.screen_capture import capture_all_monitors


def main() -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    temp_dir = Path(tempfile.gettempdir()) / "peachy_captures"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Peachy Screen Capture Diagnostic")
    print(f"Output directory: {temp_dir}")
    print("=" * 60)

    monitors = capture_all_monitors()
    if not monitors:
        print("ERROR: No monitors captured!")
        return 1

    print(f"Total monitors detected: {len(monitors)}\n")

    for idx, mon in enumerate(monitors):
        geom = mon.logical_geometry
        dpr = mon.dpr
        img = mon.image

        sanitized_name = mon.name.replace("\\", "_").replace(".", "_").strip("_")
        out_path = temp_dir / f"monitor_{idx}_{sanitized_name}.png"
        saved = img.save(str(out_path), "PNG")

        print(f"Monitor {idx}:")
        print(f"  Name:             {mon.name}")
        print(f"  Logical Geometry: x={geom.x()}, y={geom.y()}, w={geom.width()}, h={geom.height()}")
        print(f"  DevicePixelRatio: {dpr}")
        print(f"  Physical Size:    {img.width()} x {img.height()} px")
        print(f"  Saved Image:      {out_path} (Success={saved})")
        print("-" * 60)

    print("\nCapture verification complete! Please open the PNGs to verify sharpness and alignment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
