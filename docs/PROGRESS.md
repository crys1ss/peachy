# Peachy Project Progress

## Daily Status

| Day | Focus | Status |
| :--- | :--- | :--- |
| **Day 1** (Thu 22 Oct) | Architecture, desktop shell, global hotkey, state machine | **Done & Verified** |
| **Day 2** (Fri 23 Oct) | Screen capture, frozen selection overlay, multi-monitor & DPI | **Done & Verified** |
| **Day 3** (Sat 24 Oct) | Gemini provider, plain popup views, workers, end-to-end MVP | **Done & Verified** |
| **Day 4** (Sun 25 Oct) | Cute popup styling, focus handling, drag, pin, animations | **Done & Verified** |
| **Day 5** (Mon 26 Oct) | Settings window, keyring, double-tap C hook, hardening pass | **Done & Verified** |
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

### Verified by Automated Tests (66/66 pytest tests passed)
- `tests/test_gemini_provider.py` (11 tests):
  - `test_missing_key_raises_missing_key_error`: Detects absent API key.
  - `test_request_contains_image_part_text_and_model_from_settings`: Validates SDK request payloads.
  - `test_empty_question_defaults_to_explain_screen`: Verifies default prompt "Explain this screen".
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

---

## Day 4 Summary (Sunday 25 Oct)

### What Works & Is Done
1. **Design Tokens & Dark Mode ([ui/theme.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/theme.py))**:
   - Centralized theme tokens: Accent `#F472B6`, hover `#EC4899`, soft surface `#FFF1F6`, card `#FFFFFF`, text `#1F1F23`, muted `#6B6B76`, border `#F9C9DC`. Dark surface `#1E1A1D`, card `#2A2328`, text `#F5F0F3`.
   - Windows light/dark mode registry detection (`AppsUseLightTheme`) with fallback to Qt style hints.
   - Segoe UI Variable typography hierarchy (15px semibold title, 13-14px body).
2. **Sparkle Mascot Vector Asset ([resources/sparkle.svg](file:///c:/Users/TANAY/Downloads/Peachy/resources/sparkle.svg))**:
   - Clean 4-point sparkle star with companion satellite dot rendered via `QSvgRenderer` for crispness across all DPR scales.
3. **Card Shell with Soft Drop Shadow ([ui/peachy_popup.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/peachy_popup.py))**:
   - Frameless, translucent background (`Qt.WA_TranslucentBackground`), `Qt.Tool` (no taskbar item).
   - Outer layout provides 12px padding for soft multi-pass gaussian card drop shadow (`QGraphicsDropShadowEffect`).
   - 16px radius on card container.
4. **Header & Window Controls**:
   - Draggable by header, strictly clamped inside available monitor workspace (`clamp_popup_to_screen`).
   - Action buttons:
     - **Pin**: Toggles `WindowStaysOnTopHint` (pinned ON by default).
     - **Minimize**: Collapses main card into a small floating pink pill companion widget (`MinimizedPillWidget`) with sparkle icon + `"peachy"`. Clicking the pill expands it back into the main card.
     - **Close (Esc)**: Clears conversation history, closes popup, restores foreground window focus, and returns to `IDLE`.
   - **Length Chip**: Toggleable "Short" / "Detailed" chip that switches answer length instruction.
5. **Polite Focus Policy (`WA_ShowWithoutActivating`)**:
   - **AskView**: Accepts typing focus automatically upon activation so user can type immediately.
   - **AnswerView**: Renders using `Qt.WA_ShowWithoutActivating`, ensuring Chrome, VS Code, or Notepad never loses typing focus.
6. **Views & Animations**:
   - **AskView**: Dashed pink border (`2px dashed #F472B6`) around thumbnail preview, placeholder `"Ask about this..."`, hint `"Enter to send, Esc to cancel"`.
   - **ThinkingView**: Three bouncing pink dots (`BouncingDotsWidget`). Strict timer lifecycle: animation timer only runs while visible, stopped while hidden.
   - **AnswerView**: First-answer title header `"Here's the answer!"`, monospace code blocks with soft pink background, Copy button with 1.5s `"Copied!"` timed toast, rounded pill follow-up input bar.
   - **ErrorView**: Friendly message, Retry button, Cancel button.
7. **Multi-Screenshot Conversational Flow ([core/app_controller.py](file:///c:/Users/TANAY/Downloads/Peachy/core/app_controller.py))**:
   - Fixed: `on_new_screenshot()` now preserves `_current_history` while transitioning to capture, allowing continuous chat across multiple screenshots.
   - Topology listeners: Re-clamps popup when screens or geometries change.

### Verified by Automated Tests (80/80 pytest tests passed)
- `tests/test_theme.py` (4 tests):
  - `test_theme_tokens_contrast_and_palette`: Light/dark token definitions.
  - `test_get_theme_override`: Forced light and dark mode overrides.
  - `test_font_family_hierarchy`: Font family preferences.
  - `test_card_stylesheet_generation`: QSS token presence.
- `tests/test_peachy_popup.py` (9 tests):
  - `test_pure_function_clamp_popup_to_screen`: Clamping with positive and negative screen origins.
  - `test_calculate_popup_position_adjacent`: Right-first and fallback left/below placement.
  - `test_popup_frameless_and_pin_toggle`: Frameless, Tool, and stay-on-top toggle.
  - `test_view_switching_lifecycle`: Seamless Ask -> Thinking -> Answer -> Error transitions.
  - `test_bouncing_dots_timer_strictly_stopped_when_hidden`: Strict zero-timer leak when hidden.
  - `test_copy_button_clipboard_and_timed_toast`: Clipboard write and 1.5s text revert.
  - `test_minimize_and_expand_pill`: Minimize to floating pill and click-to-expand.
  - `test_length_chip_toggle`: Chip toggle between "Short" and "Detailed".
  - `test_polite_focus_answer_view_does_not_steal_focus`: `WA_ShowWithoutActivating` verification.
- `tests/test_app_controller.py`:
  - `test_new_screenshot_preserves_conversation_history`: Verified multi-screenshot conversation context retention.
- Prior Day Tests (66 tests): All Day 1-3 tests continue passing without regression.

### Verified by Screenshot Artifacts (`scripts/generate_screens.py`)
Generated 5 preview screenshots into `docs/screens/`:
- `docs/screens/ask_view.png`
- `docs/screens/thinking_view.png`
- `docs/screens/answer_view.png`
- `docs/screens/error_view.png`
- `docs/screens/minimized_pill.png`

### Needs Manual Check (Physical User Testing)
- [ ] Inspect generated images in `docs/screens/`: Confirm they match the cute white card, soft pink, sparkle aesthetic.
- [ ] Run `python app.py`:
  - Box a question, receive answer: Click into Chrome and type — verify Chrome keeps focus while popup stays visible.
  - Toggle Pin button: Unpinned popup drops behind other windows when clicked outside; pinned popup stays on top.
  - Drag popup by its header to screen edge: Confirm it stops at the screen boundary and never slips off-screen.
  - Click Minimize button (`—`): Verify it collapses to the cute pink pill; click pill to restore.
  - Click "New Screenshot": Verify screen freezes for a new crop and continues the previous conversation context.
  - Windows Dark Mode: Confirm colors adapt smoothly to dark mode.

---

## Day 5 Summary (Monday 26 Oct)

### What Works & Is Done
1. **Settings Window ([ui/settings_window.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/settings_window.py))**:
   - Styled adhering to Peachy design system (`16px` radius, `#F472B6` accent, `#FFF1F6` / `#2A2328` surfaces).
   - **Shortcut Recorder**: Interactive click-to-record button that intercepts keys, validates with `parse_shortcut`, attempts live registration, detects collisions inline, and rolls back to previous shortcut if registration fails.
   - **Double-Tap C Hook Config**: OFF by default, slider for 200–500ms (default 280ms), with warning text: *"May trigger while typing words with 'cc'"*.
   - **AI Configuration**: Masked password field for API key with eye toggle; non-blocking "Test" button verifying connection with inline green/red feedback; model dropdown populated with options and editable fallback.
   - **Popup & System Preferences**: "Pinned by default" toggle; Position radio choice ("Near selection" vs "Last used spot"); Windows startup toggle via `winreg`.
   - **Privacy Notice**: Styled callout: *"Peachy only looks at your screen when you press the shortcut. It sends only the area you select, and only when you press Send. Nothing is recorded or saved."*
2. **Secure Key Storage with Keyring ([config/key_storage.py](file:///c:/Users/TANAY/Downloads/Peachy/config/key_storage.py))**:
   - Integrates Windows Credential Manager (`keyring.backends.Windows.WinVaultKeyring`) under service name `"Peachy"`, username `"gemini_api_key"`.
   - Strict lookup precedence: Keyring vault first, then `GEMINI_API_KEY` environment variable.
   - Keys are never serialized to `settings.json`, logs, or crash dumps.
3. **Low-Level Keyboard Hook ([core/double_tap.py](file:///c:/Users/TANAY/Downloads/Peachy/core/double_tap.py) & [core/win32.py](file:///c:/Users/TANAY/Downloads/Peachy/core/win32.py))**:
   - Implements `WH_KEYBOARD_LL` via ctypes with typed `HOOKPROC`, `KBDLLHOOKSTRUCT`, `SetWindowsHookExW`, `UnhookWindowsHookEx`, and `CallNextHookEx`.
   - Pure `DoubleTapDetector` unit-tested for key transitions.
   - Guards:
     - Ignores injected events (`LLKHF_INJECTED`).
     - Ignores auto-repeat from held key.
     - Requires plain C (no Ctrl, Alt, or Win modifiers).
     - Any intervening key down resets the sequence.
     - Strong Python reference maintained on callback to prevent garbage collection.
     - Documented UIPI limitation for elevated (Administrator) windows.
4. **Hardening Pass**:
   - Friendly typed error messages:
     - Missing key: `"Gemini API key is missing. Please add your key in Settings."`
     - Rate limited 429: `"Peachy needs a breather, try again in a moment"`
     - Offline / network: `"You appear to be offline. Please check your internet connection and retry."`
     - Invalid key: `"Gemini API key is invalid or unauthorized. Please verify your key."`
   - `SelectionOverlay`: `closeEvent` cleanly cancels selection and restores foreground HWND when Alt+F4 is pressed.
   - `OverlayManager`: Topology listeners safely cancel active selection without crashing when monitors are plugged/unplugged.
   - `app.py`: `sys.excepthook` catches any unhandled Qt slot exception, logs to rotated file, displays a friendly recovery toast, and resets FSM to `IDLE`. `qInstallMessageHandler` routes Qt messages to Python logging.
   - Clean shutdown in `AppController.shutdown()` terminates active worker threads with zero orphaned processes.
5. **Privacy Audit ([tests/test_privacy_audit.py](file:///c:/Users/TANAY/Downloads/Peachy/tests/test_privacy_audit.py))**:
   - Verified automated scan of codebase and real `peachy.log`: 0 hardcoded keys, 0 unredacted tokens, 0 prompt text, 0 image bytes dumped.

### Verified by Automated Tests (107/107 pytest tests passed in 2.52s)
- `tests/test_key_storage.py` (5 tests): Keyring precedence, env fallback, none handling, save/delete operations.
- `tests/test_double_tap.py` (8 tests): Fast "c c" fires, slow "c c" does not, "c x c" does not, "ctrl+c" does not, held C auto-repeat ignored, injected events ignored, hook lifecycle.
- `tests/test_settings_window.py` (5 tests): UI initialization, recorder click/key-press, Esc cancel, conflict inline error, save and apply.
- `tests/test_hardening.py` (6 tests): Exact error messages, 8x8 threshold, Alt+F4 overlay close, monitor topology change, `sys.excepthook` crash resilience, worker termination on quit.
- `tests/test_privacy_audit.py` (3 tests): RedactionFilter coverage, hardcoded key scanner across codebase, log file verification.
- Prior Day Tests (80 tests): All Days 1-4 tests continue passing with zero regressions.

### Needs Manual Check (Physical User Testing)
- [ ] Change the shortcut to `Alt+Q` in Settings: verify it works immediately without restart.
- [ ] Pick a shortcut another app already uses: verify friendly conflict message appears inline and old shortcut is retained.
- [ ] Paste your API key in Settings and click "Test": verify green "✓ API Key is valid!" appears. Delete env var `GEMINI_API_KEY`, restart app, and verify Peachy still works.
- [ ] Enable Double-tap C and type `"success accept occur"` in Notepad: verify typing words with 'cc' does not trigger false activations.
- [ ] Change scaling or unplug a monitor while Peachy runs: verify no crash occurs and overlay/popup re-clamps cleanly.
- [ ] Quit while thinking: verify process exits cleanly with no residual python process in Task Manager.
- [ ] Enable startup in Settings: verify registry key is created under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

### Known Bugs
- None.

---

## Day 6 Summary (Tuesday 27 Oct)

### What Works & Is Done
1. **Automated Build Script ([build.ps1](file:///c:/Users/TANAY/Downloads/Peachy/build.ps1))**:
   - Clean venv creation option, pinned dependency installation from `requirements-dev.txt`.
   - Automated `pytest` execution gating the build (stops on any test failure).
   - Multi-resolution icon generation (`resources/peachy.ico` at 16, 32, 48, and 256 px) from SVG asset.
   - PyInstaller packaging in `onedir` windowed mode (`console=False`) producing `dist\Peachy\Peachy.exe`.
   - Architectural decision documented: `onedir` chosen over `onefile` for sub-second startup times and zero `%TEMP%` extraction heuristic AV false positives.
2. **Frozen Build Integrity Verification ([scripts/verify_frozen.py](file:///c:/Users/TANAY/Downloads/Peachy/scripts/verify_frozen.py))**:
   - Verified executable existence and file size (~17.2 MB).
   - Verified Qt Platform plugin (`qwindows.dll`) and Qt SVG imageformat plugin (`qsvgicon.dll`).
   - Verified bundled resources (`sparkle.svg` and `peachy.ico`) in both `_internal/resources` and adjacent `resources`.
   - Verified Windows Credential Manager keyring backend (`keyring.backends.Windows`).
3. **Inno Setup Windows Installer ([installer/peachy.iss](file:///c:/Users/TANAY/Downloads/Peachy/installer/peachy.iss))**:
   - Modern wizard installer creating Start Menu and Desktop shortcuts.
   - Optional automatic Windows startup entry.
   - Clean uninstaller removing all binaries and user startup registry entries.
4. **Comprehensive Documentation ([README.md](file:///c:/Users/TANAY/Downloads/README.md))**:
   - Application overview, architecture, and feature showcase.
   - High-fidelity screenshots from `docs/screens/` demonstrating Ask, Thinking, Answer, Error, and Pill states.
   - Step-by-step Gemini API key setup instructions (Google AI Studio).
   - Full keyboard shortcuts reference and interactive settings guide.
   - Transparent privacy breakdown (zero telemetry, zero background capture, secure Windows Credential Manager storage).
   - Troubleshooting guide covering hotkey conflicts, Administrator windows (UIPI), DRM video, SmartScreen, and log retrieval.
5. **Specification Acceptance Report ([docs/ACCEPTANCE.md](file:///c:/Users/TANAY/Downloads/Peachy/docs/ACCEPTANCE.md))**:
   - Section-by-section audit of all 33 specification requirements across Days 1 through 6.
   - 100% verified status across all core features.

### Verified by Automated Tests (107/107 pytest tests passed in 3.83s)
- `tests/test_app.py`
- `tests/test_app_controller.py`
- `tests/test_crop.py`
- `tests/test_double_tap.py`
- `tests/test_gemini_provider.py`
- `tests/test_geometry.py`
- `tests/test_hardening.py`
- `tests/test_hotkey_manager.py`
- `tests/test_hotkey_parser.py`
- `tests/test_key_storage.py`
- `tests/test_peachy_popup.py`
- `tests/test_privacy_audit.py`
- `tests/test_selection_overlay.py`
- `tests/test_settings.py`
- `tests/test_settings_window.py`
- `tests/test_state_manager.py`
- `tests/test_theme.py`

### Final Acceptance Checklist
- [x] `build.ps1` runs and outputs `dist\Peachy\Peachy.exe`.
- [x] PyInstaller onedir mode packages all Qt plugins, SVG renderers, and keyring backends.
- [x] No hardcoded API keys anywhere in codebase or logs (`tests/test_privacy_audit.py`).
- [x] 100% test pass rate (107/107 passed).
- [x] `README.md` and `docs/ACCEPTANCE.md` finalized.
- [ ] Manual smoke test: Run `dist\Peachy\Peachy.exe`, select region, ask question, and quit cleanly.
- [ ] Tag repository: `git tag v1.0`.

---

## Freehand Selection Update

### What Works & Is Done
1. **Dual Selection Modes**:
   - `Freehand` mode added as new default; legacy `Rectangle` mode preserved with 100% backwards compatibility.
   - `Tab` key toggles between Freehand and Rectangle during selection across all monitor overlays.
   - Top-centered rounded pill badge on each overlay displays active mode and controls:
     - Freehand: `"Freehand: draw around what you want. Esc cancel, Tab switch mode, Backspace clear."`
     - Rectangle: `"Rectangle: drag to select a rectangle. Esc cancel, Tab switch mode, Backspace clear."`
2. **Smooth Live Drawing & Optimization**:
   - 3 px smooth pink line (`#F472B6`, round caps and joins) rendered with `QPainterPath`.
   - Points captured in physical pixels with $\ge 2.0$ px Euclidean distance filtering.
   - Zero image copies per mouse move; dirty rectangle invalidation updates only active stroke segments.
   - Auto-closes stroke on release (last point to start point) and draws light pink tint (`#F472B6` at 35 alpha).
3. **Multi-Stroke Union (`Shift`)**:
   - Holding `Shift` on release keeps the selection open and unions additional strokes.
   - `Enter` confirms the union of shapes; `Backspace` clears all strokes; `Esc` cancels.
4. **Degenerate Stroke Rejection**:
   - Discards single clicks, straight lines, bounding boxes $< 8 \times 8$ physical px, and shapes with polygon area $< 64$ sq px.
5. **Exact Masking & Crop Output**:
   - Bounding box extracted from original frozen image.
   - Setting `"outside_shape"`:
     - `"blank"` (default): generates physical Pillow mask dilated by ~4 px (`ImageFilter.MaxFilter(9)`), composites over pure white `(255, 255, 255)`, and outputs RGB `QImage` (no alpha channel).
     - `"keep"`: returns plain bounding box crop.
   - Ramer-Douglas-Peucker (RDP) polyline simplification with pinned extreme vertices, strictly preserving the bounding box.
6. **Pure Geometry Functions ([capture/geometry.py](file:///c:/Users/TANAY/Downloads/Peachy/capture/geometry.py))**:
   - Isolated widget-free math: `add_point_if_far_enough`, `close_path`, `polygon_bounding_box`, `union_bounding_boxes`, `polygon_area`, `is_straight_line`, `is_degenerate_stroke`, `rdp_simplify`, `build_polygon_mask`, and `crop_freehand`.
7. **Settings UI & Persistence**:
   - Added `selection_mode` (`"freehand"` / `"rectangle"`) and `outside_shape` (`"blank"` / `"keep"`) to `Settings` in [config/settings.py](file:///c:/Users/TANAY/Downloads/Peachy/config/settings.py).
   - Added "Selection & Capture" section to [ui/settings_window.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/settings_window.py) with radio controls for mode and outside shape.
8. **Diagnostic Verification & Safe Debugging**:
   - [scripts/freehand_check.py](file:///c:/Users/TANAY/Downloads/Peachy/scripts/freehand_check.py) created: generates synthetic quadrant image, applies triangle stroke mask, saves PNG, and verifies inside/outside pixel colors.
   - `PEACHY_DEBUG_SAVE_CROP=1` support with automatic deletion of debug files on application exit via `atexit` and `AppController.shutdown()`.

### Verified by Automated Tests (133/133 pytest tests passed in 33.11s)
- `tests/test_geometry.py`:
  - `test_add_point_if_far_enough_filtering`: Point filtering at 2.0 px Euclidean distance.
  - `test_close_path`: Auto-connecting endpoints.
  - `test_polygon_bounding_box_directions_and_negative_origins`: Direction-agnostic boxes and negative monitor origins.
  - `test_polygon_bounding_box_across_dprs`: DPR 1.0, 1.25, 1.5, 2.0 scaling.
  - `test_polygon_area_shoelace`: Shoelace area calculation.
  - `test_is_straight_line`: Collinear straight line detection.
  - `test_degenerate_strokes_rejected`: 1 point, straight line, tiny box, tiny area.
  - `test_rdp_simplify_preserves_bounding_box_and_reduces_points`: Point reduction with guaranteed 100% bounding box preservation.
  - `test_union_bounding_boxes`: Multi-stroke bounding box union.
- `tests/test_crop.py`:
  - `test_crop_freehand_synthetic_mask_blank_and_keep`: Synthetic 4-color grid testing inside pixels preserved, outside pixels pure white (no alpha), and plain box in keep mode.
  - `test_crop_freehand_two_strokes_combine_into_one_union_box_and_mask`: Multi-stroke union mask validation.
- `tests/test_selection_overlay.py`:
  - `test_default_mode_is_freehand_and_tab_toggles`: Freehand default, Tab toggling.
  - `test_freehand_single_click_ignored`: Single click rejected.
  - `test_freehand_straight_line_ignored`: Straight line rejected.
  - `test_freehand_valid_stroke_confirmed`: Closed loop confirms and crops.
  - `test_freehand_shift_multi_stroke_union_and_enter`: Multi-stroke Shift union and Enter confirm.
  - `test_freehand_backspace_clears_strokes`: Backspace stroke clearing.
  - `test_valid_selection_confirmed` & `test_tiny_selection_rejected`: Rectangle mode backwards compatibility.
- `tests/test_app_controller.py`:
  - `test_hotkey_pressed_during_selecting_is_ignored`: Activation while in SELECTING ignored.
- `tests/test_settings.py` & `tests/test_settings_window.py`:
  - `test_default_mode_is_freehand_when_settings_missing_or_corrupt_or_invalid`: Fallback to Freehand and Blank on missing/corrupt/invalid files.
  - New selection settings fields defaults, persistence, and UI control interactions.

### Needs Manual Check (Physical User Testing)
- [ ] Run `python app.py`: Press `Ctrl+Shift+Space`:
  - Confirm top hint chip says: `"Freehand: draw around what you want. Esc cancel, Tab switch mode, Backspace clear."`
  - Draw a freehand loop: confirm smooth 3 px pink line with round caps renders without latency.
  - Release mouse: confirm loop closes automatically with light pink tint inside, unfreezes screen, and Ask popup appears.
- [ ] Press `Ctrl+Shift+Space`, press `Tab`:
  - Confirm top hint chip switches to: `"Rectangle: drag to select a rectangle. Esc cancel, Tab switch mode, Backspace clear."`
  - Drag a box: confirm rectangle selection functions normally.
  - Press `Tab` again: confirm it switches back to Freehand mode.
- [ ] Multi-Stroke: Press `Ctrl+Shift+Space`, draw shape 1, hold `Shift` on release (selection stays open). Draw shape 2 on same screen. Press `Enter`: confirm union of both shapes is captured.
- [ ] In Settings, switch "Outside shape" to "Keep", draw a freehand shape: confirm entire bounding box is preserved without white blanking.

### Known Bugs
- None.

---

## Action Presets, Instant OCR & Zero-Slop Update

### What Works & Is Done
1. **Quick Action Preset Chips ([ui/peachy_popup.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/peachy_popup.py))**:
   - Added 5 flat, zero-gradient action chips directly to `AskView`:
     - 🎯 **Solve**: Auto-generates prompt to state the correct answer/option first, then explain concisely.
     - 💻 **Fix Code**: Identifies bugs/errors, states root cause, and outputs drop-in code fix.
     - 🌐 **Translate**: Translates visible text into fluent English with zero commentary.
     - 📝 **Summarize**: Summarizes key takeaways into concise bullet points.
     - 📋 **Copy Text**: Verbatim text extraction without commentary.
   - Combines user-typed context with preset prompt if input field is populated.
2. **Instant OCR & Clipboard Auto-Copy ([core/app_controller.py](file:///c:/Users/TANAY/Downloads/Peachy/core/app_controller.py))**:
   - When a Copy Text request completes, `AppController` automatically populates `QGuiApplication.clipboard()` with the raw extracted text.
   - Answer view automatically displays title *"Extracted Text (Copied to Clipboard)"*.
3. **Removal of AI Slop**:
   - `AnswerView`: Replaced cartoonish *"Here's the answer!"* heading with direct, professional title *"Answer"*.
   - Header Bar: Removed generic *"Screen assistant"* subtitle to de-clutter branding.
   - System Prompt ([ai/gemini_provider.py](file:///c:/Users/TANAY/Downloads/Peachy/ai/gemini_provider.py)): Enforces zero conversational filler, pleasantries, sycophancy, or preamble (bans "Sure!", "Here is...", "Hope this helps").
4. **Zero-Gradient Flat Aesthetic ([ui/theme.py](file:///c:/Users/TANAY/Downloads/Peachy/ui/theme.py))**:
   - Guaranteed 100% solid flat surfaces and buttons with crisp borders.
   - Verified 0 CSS gradients across the entire stylesheet.
5. **Foreground Window Context ([core/win32.py](file:///c:/Users/TANAY/Downloads/Peachy/core/win32.py))**:
   - Added `GetWindowTextLengthW` and `GetWindowTextW` Win32 ctypes wrappers with `argtypes` and `restype`.
   - `on_activated` retrieves active window title (`self._saved_foreground_title`).

### Verified by Automated Tests (132/132 pytest tests passed in 3.26s)
- `tests/test_peachy_popup.py`:
  - `test_preset_action_chips_dispatch_custom_prompts`: Verified all 5 action chips and user text combination.
  - `test_ocr_header_title_display`: Verified OCR question header adaptation.
  - `test_view_switching_lifecycle`: Verified "Answer" header title.
- `tests/test_app_controller.py`:
  - `test_copy_text_auto_clipboard_copy`: Verified automatic clipboard population on OCR completion.
- `tests/test_theme.py`:
  - `test_theme_no_gradients_and_solid_preset_chips`: Verified zero gradients and solid presetChip styling.
- All 128 prior tests continue to pass without regression.

### Needs Manual Check (Physical User Testing)
- [ ] Press `Ctrl+Shift+Space`, select text or a problem:
  - Confirm the 5 preset chips (`🎯 Solve`, `💻 Fix Code`, `🌐 Translate`, `📝 Summarize`, `📋 Copy Text`) appear neatly under the input field.
  - Click `📋 Copy Text`: confirm text is extracted and automatically copied to clipboard. Press `Ctrl+V` in Notepad to verify.
  - Click `🎯 Solve`: confirm model returns the direct answer without "Here's the answer!" or chatty preamble.
  - Verify popup title is clean `"peachy"` without "Screen assistant" subtitle.

### Known Bugs & Fixes
- **Fixed (Auto-recovery from ERROR state)**: If an AI request failed (e.g. missing API key, network timeout), the app previously remained stuck in `ERROR` state if the user didn't explicitly click "Cancel" on the popup. Pressing the hotkey would log `Activation ignored: state is ERROR (must be IDLE)`. Now:
  1. Pressing the global hotkey or tray "Ask Peachy" while in `ERROR` state automatically dismisses the error, resets to `IDLE`, and starts a fresh capture immediately.
  2. Saving settings in `SettingsWindow` automatically resets an active `ERROR` state to `IDLE`.
  3. `PeachyPopup` and `ErrorView` now catch `closeEvent` and `Esc` to reliably emit `cancelled` and return to `IDLE`.
  4. Verified by unit test `test_hotkey_while_in_error_state_auto_resets_and_activates`.

### Total Automated Tests (134/134 pytest tests passed in 3.21s)
- 134 passed with 100% pass rate across geometry, overlay, hotkey, provider, settings, and FSM lifecycle tests.



