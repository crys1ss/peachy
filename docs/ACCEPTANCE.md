# Peachy Acceptance Report

This document audits the completed Peachy application against the requirements in [`docs/SPEC.md`](file:///c:/Users/TANAY/Downloads/Peachy/docs/SPEC.md).

---

## 1. Specification Audit Matrix

| Section | Requirement | Status | Verification Method |
| :--- | :--- | :--- | :--- |
| **1. Target Platform** | Windows 10/11, Python 3.12+, PySide6 desktop application (no web/Electron) | **Done** | `app.py`, `ctypes` Win32 bindings, pytest suite |
| **1. Single Window Design**| Single Peachy popup window switching between Ask, Thinking, Answer, and Error views | **Done** | `tests/test_peachy_popup.py::test_view_switching_lifecycle` |
| **1. Logging & Redaction** | Rotated logs at `%LOCALAPPDATA%\Peachy\logs` with key/token redaction filter | **Done** | `tests/test_app.py`, `tests/test_privacy_audit.py` |
| **1. Settings Storage** | Atomic saving (`os.replace`) to `%APPDATA%\Peachy\settings.json`, auto backup on corruption | **Done** | `tests/test_settings.py` (7 tests) |
| **1. Single Instance** | IPC server/socket guard; second launch signals primary instance to open Settings and exits 0 | **Done** | `scripts/verify_day1.py::test_single_instance_guard` |
| **1. System Tray** | Sparkle tray icon with context menu (Ask, Settings, Pause Hotkey, Quit) | **Done** | `ui/tray_manager.py`, manual verification |
| **1. Win32 Layer** | Strict ctypes Win32 calls in `core/win32.py` with argtypes, restype, and error checks | **Done** | `core/win32.py` |
| **1. Global Hotkey** | Register `Ctrl+Shift+Space` with `MOD_NOREPEAT`, parse strings, handle conflicts gracefully | **Done** | `tests/test_hotkey_manager.py`, `tests/test_hotkey_parser.py` |
| **1. State Machine** | 7-state FSM (`IDLE`, `CAPTURING`, `SELECTING`, `ASKING`, `THINKING`, `ANSWERING`, `ERROR`) | **Done** | `tests/test_state_manager.py` (7 tests) |
| **2. Screen Capture** | Capture all monitors synchronously before showing UI (<150ms for 1080p) | **Done** | `capture/screen_capture.py`, `scripts/capture_check.py` |
| **2. Multi-Monitor & DPI** | Pure coordinate normalization, clamping with negative origins, exact DPR conversions | **Done** | `tests/test_geometry.py` (9 tests) |
| **2. Frozen Overlay** | Topmost frameless overlay per screen, 35% black dimming, 2px pink border, dimension badge | **Done** | `tests/test_selection_overlay.py` (7 tests) |
| **2. Selection Guards** | Enforce 8x8 physical pixel minimum size threshold; ignore tiny drags | **Done** | `tests/test_geometry.py::test_is_valid_selection_threshold` |
| **2. Overlay Cancellation**| Esc, Right-Click, Alt+F4, or 60s inactivity timeout cancels and restores foreground focus | **Done** | `tests/test_selection_overlay.py`, `tests/test_hardening.py` |
| **3. AI Provider Interface**| Abstract `BaseAIProvider` with typed errors (`MissingKey`, `InvalidKey`, `RateLimited`, etc.) | **Done** | `ai/provider.py`, `tests/test_gemini_provider.py` |
| **3. Gemini SDK** | Official `google-genai` SDK with `client.models.generate_content`, AFC disabled | **Done** | `tests/test_gemini_provider.py` (11 tests) |
| **3. Model Configuration** | `model` from settings, overridable by `PEACHY_MODEL` env var | **Done** | `tests/test_gemini_provider.py::test_model_name_env_override` |
| **3. Image Optimization** | Downscale only if long side > 2048 px; never upscale small crops | **Done** | `tests/test_gemini_provider.py::test_prepare_image_downscale_only` |
| **3. Background Workers** | Network and slow AI operations run off UI thread via `QThread` with signals | **Done** | `core/worker.py`, `tests/test_app_controller.py` |
| **3. Multimodal Conversation**| Multi-turn conversation history carried across follow-ups | **Done** | `tests/test_app_controller.py` |
| **4. Visual Identity** | Central theme tokens in `ui/theme.py`, `#F472B6` pink accent, Segoe UI Variable font | **Done** | `tests/test_theme.py` (4 tests) |
| **4. Sparkle Mascot** | 4-point sparkle star SVG asset with satellite dot in `resources/` | **Done** | `resources/sparkle.svg`, `scripts/generate_ico.py` |
| **4. Card Styling** | 16px radius, soft drop shadow, 380px width, max 60% screen height, scrollable answer area | **Done** | `tests/test_peachy_popup.py`, `docs/screens/` |
| **4. Polite Focus** | Answer view appears without stealing focus (`WA_ShowWithoutActivating`); Ask view takes focus | **Done** | `tests/test_peachy_popup.py::test_polite_focus_answer_view_does_not_steal_focus` |
| **4. Clamped Dragging** | Header dragging clamped inside monitor work area, re-clamping on topology change | **Done** | `tests/test_peachy_popup.py::test_pure_function_clamp_popup_to_screen` |
| **4. Pin & Minimize** | Pin stays on top by default; minimize collapses to floating pink pill (`✨ peachy`) | **Done** | `tests/test_peachy_popup.py::test_minimize_and_expand_pill` |
| **4. New Screenshot Flow** | "New Screenshot" hides popup, triggers selection, continues same conversation | **Done** | `tests/test_app_controller.py::test_new_screenshot_preserves_conversation_history` |
| **5. Settings Window** | Shortcut recorder with live validation and collision rollback; model dropdown | **Done** | `tests/test_settings_window.py` (5 tests) |
| **5. Secure Key Storage** | Keyring with Windows Credential Manager (`WinVaultKeyring`); order: keyring then env | **Done** | `tests/test_key_storage.py` (5 tests) |
| **5. Double-Tap C Hook** | Low-level `WH_KEYBOARD_LL` hook with strict guards (rejects injected, held auto-repeat, modifiers) | **Done** | `tests/test_double_tap.py` (8 tests) |
| **5. Hardening Pass** | Friendly error messages, Alt+F4 recovery, topology safety, `sys.excepthook` crash prevention | **Done** | `tests/test_hardening.py` (6 tests) |
| **5. Privacy Audit** | Codebase and real log audit confirming 0 keys, 0 prompt text, 0 dumped image bytes | **Done** | `tests/test_privacy_audit.py` (3 tests) |
| **6. Packaging** | Automated PowerShell build (`build.ps1`) producing onedir distribution in `dist\Peachy\` | **Done** | `build.ps1`, `Peachy.spec` |
| **6. Documentation** | Comprehensive `README.md` with screenshots, shortcuts, troubleshooting, and privacy details | **Done** | `README.md` |

---

## 2. Automated Test Suite Summary

- **Total Test Cases**: 107
- **Passed**: 107 (100%)
- **Failed**: 0
- **Execution Time**: ~3.4 seconds
- **Platform**: Windows 11 (64-bit), Python 3.13, PySide6 6.8.2.1

---

## 3. Known Limitations & Documented Windows Behaviors

1. **User Interface Privilege Isolation (UIPI)**:
   - Keystrokes in Administrator windows are invisible to low-level keyboard hooks installed by standard user processes. Peachy must be run as Administrator if system-wide monitoring over elevated apps is required.
2. **Hardware-Protected DRM Video**:
   - Protected streaming video playback (e.g. Netflix in browser) is rendered via protected overlays and captured black by design of Windows Desktop Duplication and GDI APIs.
3. **Unsigned SmartScreen Warning**:
   - Because the open-source executable does not possess an expensive EV code-signing certificate, Windows SmartScreen will display an informational prompt on first execution.
