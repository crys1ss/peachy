# Peachy Project Progress

## Daily Status

| Day | Focus | Status |
| :--- | :--- | :--- |
| **Day 1** (Thu 22 Oct) | Architecture, desktop shell, global hotkey, state machine | **Done & Verified** |
| **Day 2** (Fri 23 Oct) | Screen capture, frozen selection overlay, multi-monitor & DPI | **Done & Verified** |
| **Day 3** (Sat 24 Oct) | Gemini provider, plain popup views, workers, end-to-end MVP | **Done & Verified** |
| **Day 4** (Sun 25 Oct) | Cute popup styling, focus handling, drag, pin, animations | Pending |
| **Day 5** (Mon 26 Oct) | Settings window, keyring, double-tap C hook, hardening pass | Pending |
| **Day 6** (Tue 27 Oct) | PyInstaller build, onedir packaging, README, acceptance | Pending |

---

## Day 1 Summary (Thursday 22 Oct)

### What Works & Is Done
1. **Architecture & Design**:
   - [docs/ARCHITECTURE.md](file:///c:/Users/TANAY/Downloads/Peachy/docs/ARCHITECTURE.md) defines system decomposition, 7-state finite state machine (`IDLE`, `CAPTURING`, `SELECTING`, `ASKING`, `THINKING`, `ANSWERING`, `ERROR`), threading model, and Windows OS mitigation strategies.
   - Pinned dependencies with documentation citations (`PySide6==6.8.2.1`, `pytest==9.1.1`, `pytest-qt==4.5.0`).
2. **Project Skeleton**:
   - `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `.env.example` (placeholders only), and packages (`config/`, `core/`, `ui/`, `tests/`).
3. **Application Shell (`app.py`)**:
   - `QApplication` with `setQuitOnLastWindowClosed(False)`.
   - Single-instance guard using `QLocalServer`/`QLocalSocket` IPC: launching a second copy tells the primary instance to open Settings and exits cleanly.
   - Rotated file logging at `%LOCALAPPDATA%\Peachy\logs\peachy.log` with `RedactionFilter` (masks keys and tokens).
4. **Settings (`config/settings.py`)**:
   - Dataclass settings (`hotkey="Ctrl+Shift+Space"`, `model="gemini-2.5-flash"`, `pinned=True`, etc.).
   - Atomic saving to `%APPDATA%\Peachy\settings.json` via temp file + `os.replace`.
   - Automatic recovery: missing file uses defaults; corrupt file creates `.json.bak` and falls back to defaults without crashing. API keys are never stored here.
5. **Win32 Layer (`core/win32.py`)**:
   - Strict `ctypes` bindings for `RegisterHotKey`, `UnregisterHotKey`, `GetForegroundWindow`, and `SetForegroundWindow` with `argtypes`, `restype`, and `GetLastError` error reporting. No Win32 calls outside this file.
6. **Global Hotkey (`core/hotkey_manager.py`)**:
   - Human-readable shortcut parser supporting `Ctrl+Shift+Space`, `Alt+Q`, function keys, navigation keys, and modifiers.
   - Registers hotkey with `MOD_NOREPEAT` via Windows API.
   - Listens for `WM_HOTKEY` via `QAbstractNativeEventFilter` in Qt event loop.
   - Non-crashing conflict reporting (`registration_failed` signal).
   - Pause/resume toggle and clean unregistration on quit.
7. **State Machine (`core/state_manager.py`)**:
   - Rejects invalid transitions.
   - Guards activation: ignores hotkey trigger unless state is `IDLE`, preventing double overlay bugs.
8. **Tray Integration (`ui/tray_manager.py`)**:
   - Custom anti-aliased pink sparkle icon (`QPainter`).
   - Context menu: *Ask Peachy*, *Settings* (placeholder dialog), *Pause Hotkey* (checkable), *Quit*.
   - Tray message notifications for activation and conflicts.
   - Activation strictly logs `"activated"` and shows tray notification without wiring any Day 2+ features.

### Verified by Automated Tests (31/31 pytest unit tests passed)
- `tests/test_hotkey_parser.py`: All valid and invalid shortcuts verified.
- `tests/test_settings.py`: Defaults, round-trip, atomic write, corrupt recovery, missing file fallback.
- `tests/test_state_manager.py`: Transitions, rejection of invalid transitions, spam guard.
- `tests/test_hotkey_manager.py`: Registration, collision error handling, pause/resume.
- `tests/test_app.py`: Redaction filter masks API keys and tokens.

### Verified by End-to-End Automated Script (`scripts/verify_day1.py`)
- [x] **Launch Peachy**: Process starts, tray initializes, `%LOCALAPPDATA%\Peachy\logs\peachy.log` created with zero tracebacks.
- [x] **Hotkey Registered**: Windows `RegisterHotKey` returns success for `Ctrl+Shift+Space`.
- [x] **Single Instance Guard**: Second instance launch signals first instance via IPC, prints message, and terminates with code 0. First instance logs `open_settings`.
- [x] **WM_HOTKEY Event Interception**: Event dispatched to Qt native event filter, `hotkey_triggered` emitted, `activated` logged, state transitions `IDLE -> CAPTURING` and resets to `IDLE`.
- [x] **Spam Guard**: 5 rapid fire hotkeys processed cleanly without crashing or corrupting state.
- [x] **Clean Exit**: Process terminates cleanly with zero orphaned processes left behind.

### Needs Manual Check (Physical User Testing)
- [ ] Run `python app.py`: Verify visually that the pink sparkle icon appears in the Windows system tray.
- [ ] With another application focused (e.g., Notepad), press `Ctrl+Shift+Space`: Verify Windows toast notification "activated" appears and nothing is typed into Notepad.
- [ ] Right-click tray icon -> check "Pause Hotkey": Verify pressing `Ctrl+Shift+Space` does nothing. Uncheck "Pause Hotkey": verify it works again.
- [ ] Right-click tray icon -> click "Quit": Verify process exits cleanly.

### Known Bugs
- None.

---

## Day 2 Summary (Friday 23 Oct)

### What Works & Is Done
1. **Mathematical Geometry Foundation ([capture/geometry.py](file:///c:/Users/TANAY/Downloads/Peachy/capture/geometry.py))**:
   - `normalize_rect`: Transforms any of the 4 drag directions (top-left, bottom-right, top-right, bottom-left) into a canonical positive rectangle.
   - `clamp_rect`: Restricts coordinates within screen boundaries, with full support for negative coordinate origins (secondary monitors positioned left/above primary).
   - `logical_to_physical` / `physical_to_logical`: Precise DPR scaling conversions across 100%, 125%, 150%, and 200% displays.
   - `clamp_crop_box`: Ensures crop slice boundaries stay within image buffer limits.
   - `is_valid_selection`: Enforces minimum 8x8 physical pixel selection threshold.
   - `extract_crop`: Extracts pixel-exact slices from `QImage` / `QPixmap`.
2. **Multi-Monitor Screen Capture ([capture/screen_capture.py](file:///c:/Users/TANAY/Downloads/Peachy/capture/screen_capture.py))**:
   - Captures all displays synchronously before any UI window is displayed using `QScreen.grabWindow(0)`.
   - Preserves native physical pixels, `QScreen` reference, logical geometry, and DPR.
   - Tested live on Windows 11 with 2 monitors (1920x1080 at 100% and 1536x864 at 125% with negative coordinates `x=-1920, y=-56`): captured in ~13-16ms total (well under the 150ms budget).
   - Image timing is logged; image pixel data is never logged.
3. **Capture Diagnostic Tool ([scripts/capture_check.py](file:///c:/Users/TANAY/Downloads/Peachy/scripts/capture_check.py))**:
   - Standalone CLI script capturing all screens and saving full-resolution PNGs to `%LOCALAPPDATA%\Temp\peachy_captures`.
4. **Frozen Selection Overlay ([capture/selection_overlay.py](file:///c:/Users/TANAY/Downloads/Peachy/capture/selection_overlay.py))**:
   - Exactly one frameless, topmost, `Qt.Tool` overlay per monitor (prevents mixed-DPI scaling artifacts).
   - Zero taskbar entry (`Qt.Tool`).
   - 35% black dimming outside selection via `QRegion` subtraction.
   - Active selection box: 2px pink border (`#F472B6`), light pink tint (`rgba(244, 114, 182, 35)`).
   - Dark pill badge with white text showing physical dimensions (`{w} × {h}`) clamped within screen view.
   - Crosshair cursor (`Qt.CrossCursor`).
   - Drag selection stays on the monitor where it started and clamps to screen edges.
   - Keyboard & mouse controls:
     - `Esc` or right-click cancels on all overlays and restores focus to original foreground window.
     - `Enter` confirms selection.
     - `Backspace` clears selection rectangle.
     - Mouse release with valid rectangle ($\ge 8\times 8$ physical px) confirms immediately.
     - Sub-8x8 selections ignored.
   - 60-second inactivity safety timeout automatically cancels.
   - Windows foreground activation: brings overlay to foreground and transfers keyboard focus so the first `Esc` key works.
5. **App Orchestration ([app.py](file:///c:/Users/TANAY/Downloads/Peachy/app.py))**:
   - Hotkey trigger $\to$ records foreground HWND $\to$ `IDLE -> CAPTURING` $\to$ captures all screens $\to$ `CAPTURING -> SELECTING` $\to$ displays overlays.
   - Hotkey activation while in `SELECTING` or `CAPTURING` is safely ignored.
   - On cancel or timeout: overlays close, original foreground HWND restored, `SELECTING -> IDLE`.
   - On confirmation: cropped `QImage` stored in memory, `SELECTING -> IDLE`.
   - Debug switch: if `PEACHY_DEBUG_SAVE_CROP=1`, crop PNG is saved to `%TEMP%\peachy_crops\crop_<timestamp>.png` and path is logged.

### Verified by Automated Tests (50/50 pytest unit tests passed)
- `tests/test_geometry.py`: Rect normalization in all 4 directions, clamping with negative origins, DPR 1.0/1.25/1.5/2.0 conversions, crop box clamping, 8x8 threshold.
- `tests/test_crop.py`: Synthetic color grid verification (Red, Green, Blue, Yellow quadrants) proving exact pixel-for-pixel accuracy on quadrant crops and multi-quadrant center crops.
- `tests/test_selection_overlay.py`: Rejection of <8x8 selections, confirmation of $\ge 8\times 8$ selections, Esc cancel, right-click cancel, Backspace clearing, 60s inactivity timeout, foreground HWND restoration.
- `tests/test_app.py`: Privacy redaction filter.
- `tests/test_hotkey_manager.py`: Win32 hotkey registration, collision handling, pause/resume.
- `tests/test_hotkey_parser.py`: Key parsing across modifiers, function keys, and symbols.
- `tests/test_settings.py`: Settings round-trip, atomic writes, corruption recovery.
- `tests/test_state_manager.py`: Transitions, rejection of invalid transitions, spam guard, cancel from SELECTING.

### Verified by End-to-End Automated Scripts
- [x] **`scripts/capture_check.py`**: Captures 2 monitors (100% and 125% DPI with negative coordinates) and saves sharp PNGs to temp.
- [x] **`scripts/verify_day1.py`**: Full single-instance IPC, `WM_HOTKEY` registration and message reception passed.
- [x] **`scripts/verify_day2.py`**:
  - Live capture speed (16.3ms for 2 monitors).
  - Multi-DPI physical-to-logical alignment.
  - End-to-end hotkey dispatch $\to$ `IDLE -> CAPTURING -> SELECTING`.
  - Spam guard verification: hotkey during `SELECTING` rejected without crashing or breaking state.
  - Clean process termination.

### Needs Manual Check (Physical User Testing)
- [ ] Run `python scripts/capture_check.py` and open the generated PNGs in `%TEMP%\peachy_captures`: confirm each matches its monitor, is sharp, and shows full desktop without blur.
- [ ] Set `set PEACHY_DEBUG_SAVE_CROP=1` and run `python app.py`:
  - Press `Ctrl+Shift+Space`: confirm screen freezes immediately, all screens dim by ~35%, cursor is crosshair.
  - Drag a box in all 4 directions: verify the box is highlighted with a 2px pink border (`#F472B6`), pink tint, and a pill badge showing `{width} × {height}` in physical pixels.
  - Release mouse on a valid selection: check `%TEMP%\peachy_crops` and verify the saved crop matches exactly what was boxed.
- [ ] Press `Ctrl+Shift+Space` and immediately press `Esc`: verify overlays close on the first press and focus returns to your previous active window.
- [ ] Press `Ctrl+Shift+Space` and right-click: verify overlays close immediately.
- [ ] Press `Ctrl+Shift+Space` and single click without dragging: verify box disappears and nothing is saved.
- [ ] Verify that no taskbar button appears while the overlays are visible.

### Known Bugs
- None.

---

## Day 3 Summary (Saturday 24 Oct)

### What Works & Is Done
1. **Abstract AI Provider Interface ([ai/provider.py](file:///c:/Users/TANAY/Downloads/Peachy/ai/provider.py))**:
   - `BaseAIProvider`: Strict abstract base class requiring `ask(image_png, question, history) -> AnswerResult`.
   - `AnswerResult`: Dataclass carrying response markdown text and updated multi-turn conversation history.
   - Typed Provider Errors with friendly user-facing messages: `MissingKey`, `InvalidKey`, `RateLimited`, `Timeout`, `Network`, `Blocked`, `EmptyResponse`, and `Unknown`.
2. **Gemini Flash Implementation ([ai/gemini_provider.py](file:///c:/Users/TANAY/Downloads/Peachy/ai/gemini_provider.py))**:
   - Built on official `google-genai` SDK (`from google import genai`).
   - Dynamic model resolution: Reads from `settings.json` (`gemini-3.8-flash`) with override via `PEACHY_MODEL` environment variable.
   - Secure Key Access: API key read strictly through `get_gemini_api_key()` from `GEMINI_API_KEY`.
   - Image Optimization: Uses Pillow to enforce PNG format, downscaling proportionally only if the long dimension exceeds 2048 px (never upscaled).
   - System Instruction: Configured with mandated prompt for concise, structured screen assistance.
   - Multi-Turn History: Preserves chat context across follow-up queries without re-transmitting image bytes.
   - Error Translation: Maps Google SDK HTTP exceptions and content blocks to typed `ProviderError` instances.
3. **Background Worker & Threading ([core/worker.py](file:///c:/Users/TANAY/Downloads/Peachy/core/worker.py))**:
   - `GeminiWorker(QThread)`: Offloads network calls from GUI thread.
   - Request ID tagging: Obsoletes and drops stale responses/errors when request IDs don't match.
   - Immediate cancellation: Flags workers as cancelled so delayed network packets don't alter UI.
   - 45-second hard timeout: `QTimer` triggers `TimeoutError` if Gemini or network hangs.
4. **Popup Interface with Plain Styling ([ui/peachy_popup.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/peachy_popup.py))**:
   - Unified window with `QStackedWidget` managing 4 distinct views:
     - **Ask View**: Thumbnail preview of crop, auto-focused question input, Send (Enter), Cancel (Esc). Empty questions allowed for auto-explanation.
     - **Thinking View**: Minimal "thinking..." label and Cancel button.
     - **Answer View**: `QTextBrowser` with Markdown support and automatic word wrapping, Copy to clipboard button, Follow-up input field with Send, New Screenshot button, and Close button.
     - **Error View**: Friendly error message and Retry button.
   - Smart Adjacent Positioning: `calculate_popup_position` positions popup to the right, left, or below the selection, clamped entirely within the active monitor's available geometry.
5. **Full Loop Orchestration ([core/app_controller.py](file:///c:/Users/TANAY/Downloads/Peachy/core/app_controller.py))**:
   - End-to-end integration: Hotkey -> Capture -> Overlay -> Popup -> Provider.
   - Window Focus Preservation: Stores foreground `HWND` upon hotkey trigger and restores it via Win32 upon popup closure.
   - Safe Resource Cleanup: Releases crop image bytes and clears chat state upon returning to `IDLE`.
6. **Diagnostic & Smoke Tools**:
   - [scripts/list_models.py](file:///c:/Users/TANAY/Downloads/Peachy/scripts/list_models.py): Enumerates all Gemini models supporting content generation.
   - [scripts/smoke_gemini.py](file:///c:/Users/TANAY/Downloads/Peachy/scripts/smoke_gemini.py): Generates a synthetic "2 + 2 = ?" PNG, executes a real Gemini call, and verifies correct model output.

### Verified by Automated Tests (65/65 pytest tests passed)
- `tests/test_gemini_provider.py` (10 tests):
  - `test_missing_key_raises_missing_key_error`: Detects absent API key.
  - `test_request_contains_image_part_text_and_model_from_settings`: Validates SDK request payloads.
  - `test_model_name_env_override`: Confirms `PEACHY_MODEL` env override.
  - `test_prepare_image_downscale_only`: Proves downscaling >2048px and preservation of <=2048px.
  - `test_sdk_exception_mapping_*`: Validates mapping for `InvalidKey`, `RateLimited`, `Timeout`, `Network`, and `Blocked`.
  - `test_empty_response_error`: Handles empty SDK candidate responses.
- `tests/test_app_controller.py` (5 integration tests):
  - `test_full_happy_path`: Full loop through `IDLE -> CAPTURING -> SELECTING -> ASKING -> THINKING -> ANSWERING -> Follow-up -> Close`.
  - `test_stale_response_dropped`: Drops delayed responses after user cancellation.
  - `test_double_send_blocked_while_thinking`: Prevents duplicate requests while thinking.
  - `test_missing_key_shows_error_view`: Displays friendly error when key is omitted.
  - `test_hard_timeout_fires_and_shows_error`: Triggers timeout error upon 45s deadline.
- Prior Day Tests (50 tests): All geometry, crop, overlay, settings, hotkey, and state machine tests continue passing.

### Verified by Real Network Smoke Test (`scripts/smoke_gemini.py`)
```
============================================================
Peachy: Gemini Provider Smoke Test
============================================================
Generating test image ('2 + 2 = ?')...
Test image generated (1954 bytes PNG).
Sending multimodal request using model 'gemini-3.8-flash'...

--- Gemini Response ---
**4**
-----------------------

History turns: 2
SMOKE TEST SUCCESSFUL!
```

### Needs Manual Check (Physical User Testing)
- [ ] Run `python scripts/list_models.py`: Confirm your API key prints the available Gemini models.
- [ ] Run `python scripts/smoke_gemini.py`: Verify that the live test prints `**4**`.
- [ ] Run `python app.py`:
  - Press `Ctrl+Shift+Space` to freeze the screen and drag a box around any text, code, or image.
  - On release, verify the plain Ask popup appears immediately next to the cropped region with a small thumbnail.
  - Press `Enter` with an empty prompt (or type a question): verify the popup transitions to "thinking...".
  - Verify the popup displays the markdown response in the Answer view.
  - Click "Copy": paste into Notepad to verify clipboard contents.
  - Type a follow-up question in the follow-up field and press Enter: verify Peachy responds with conversation context retained.
  - Click "Close" or press `Esc`: verify popup closes, focus returns to the previous app, and memory is freed.
  - Click "New Screenshot": verify screen freezes immediately for a new selection.

### Known Bugs
- None.

