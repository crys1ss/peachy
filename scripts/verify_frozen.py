"""Verify the PyInstaller frozen distribution build integrity for Peachy."""

from __future__ import annotations

from pathlib import Path
import sys


def verify_frozen_distribution() -> bool:
    dist_dir = Path("dist/Peachy")
    exe_path = dist_dir / "Peachy.exe"

    print("==========================================================")
    print(" PEACHY FROZEN BUILD INTEGRITY VERIFICATION")
    print("==========================================================")

    checks = []

    # 1. Main executable exists
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f" [PASS] Executable: {exe_path} ({size_mb:.2f} MB)")
        checks.append(True)
    else:
        print(f" [FAIL] Executable missing: {exe_path}")
        checks.append(False)

    # 2. Windows platform plugin exists (critical for Qt windowing)
    platforms_dir = dist_dir / "PySide6" / "plugins" / "platforms"
    qwindows = platforms_dir / "qwindows.dll"
    if qwindows.exists():
        print(f" [PASS] Qt Platforms Plugin: {qwindows}")
        checks.append(True)
    else:
        # Check alternative PySide6 layout
        alt_qwindows = list(dist_dir.glob("**/qwindows.dll"))
        if alt_qwindows:
            print(f" [PASS] Qt Platforms Plugin located at: {alt_qwindows[0]}")
            checks.append(True)
        else:
            print(" [FAIL] qwindows.dll platform plugin missing!")
            checks.append(False)

    # 3. SVG image format plugin (for sparkle mascot)
    svg_plugins = list(dist_dir.glob("**/qsvg*.dll"))
    if svg_plugins:
        print(f" [PASS] Qt SVG Plugin: {svg_plugins[0]}")
        checks.append(True)
    else:
        print(" [FAIL] qsvg imageformat plugin missing!")
        checks.append(False)

    # 4. Resources bundled
    sparkle_svg = dist_dir / "resources" / "sparkle.svg"
    peachy_ico = dist_dir / "resources" / "peachy.ico"
    internal_sparkle = dist_dir / "_internal" / "resources" / "sparkle.svg"
    internal_ico = dist_dir / "_internal" / "resources" / "peachy.ico"
    if (sparkle_svg.exists() and peachy_ico.exists()) or (internal_sparkle.exists() and internal_ico.exists()):
        found_sparkle = sparkle_svg if sparkle_svg.exists() else internal_sparkle
        found_ico = peachy_ico if peachy_ico.exists() else internal_ico
        print(f" [PASS] Resources: {found_sparkle} and {found_ico}")
        checks.append(True)
    else:
        print(" [FAIL] Bundled resources missing!")
        checks.append(False)

    # 5. Keyring backend files
    keyring_files = list(dist_dir.glob("**/keyring*"))
    if keyring_files:
        print(f" [PASS] Keyring components found ({len(keyring_files)} entries)")
        checks.append(True)
    else:
        print(" [FAIL] Keyring packages not found in bundle!")
        checks.append(False)

    all_passed = all(checks)
    print("----------------------------------------------------------")
    if all_passed:
        print(" ALL FROZEN BUILD VERIFICATIONS PASSED!")
    else:
        print(" SOME VERIFICATION CHECKS FAILED.")
    print("==========================================================")
    return all_passed


if __name__ == "__main__":
    success = verify_frozen_distribution()
    sys.exit(0 if success else 1)
