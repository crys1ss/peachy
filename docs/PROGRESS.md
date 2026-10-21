# Peachy Project Progress

## Daily Status

| Day | Focus | Status |
| :--- | :--- | :--- |
| **Day 1** (Thu 22 Oct) | Architecture, desktop shell, global hotkey, state machine | **Done** |
| **Day 2** (Fri 23 Oct) | Screen capture, frozen selection overlay, multi-monitor & DPI | Pending |
| **Day 3** (Sat 24 Oct) | Gemini provider, plain popup views, workers, end-to-end MVP | Pending |
| **Day 4** (Sun 25 Oct) | Cute popup styling, focus handling, drag, pin, animations | Pending |
| **Day 5** (Mon 26 Oct) | Settings window, keyring, double-tap C hook, hardening pass | Pending |
| **Day 6** (Tue 27 Oct) | PyInstaller build, onedir packaging, README, acceptance | Pending |

---

## Day 1 Summary (Thursday 22 Oct)

### What Works & Is Done
1. **Architecture & Design**:
   - Authored and committed [docs/ARCHITECTURE.md](file:///c:/Users/TANAY/Downloads/Peachy/docs/ARCHITECTURE.md).
   - Designed 7-state finite state machine (`IDLE`, `CAPTURING`, `SELECTING`, `ASKING`, `THINKING`, `ANSWERING`, `ERROR`).
   - Defined single-popup architecture using `QStackedWidget` for views.
   - Pinned dependencies with documentation citations (`PySide6==6.8.2.1`, `pytest==9.1.1`, `pytest-qt==4.5.0`).
2. **Project Skeleton**:
   - `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `.env.example`, and package packages (`config/`, `core/`, `ui/`, `tests/`).
3. **Application Shell (`app.py`)**:
   - `QApplication` running with `setQuitOnLastWindowClosed(False)`.
   - Single-instance guard using `QLocalServer`/`QLocalSocket` IPC: launching a second copy tells the primary instance to open Settings and exits cleanly.
   - Rotated file logging at `%LOCALAPPDATA%\Peachy\logs\peachy.log` with `RedactionFilter` (masks API keys and auth tokens).
4. **Settings (`config/settings.py`)**:
   - Dataclass settings (`hotkey="Ctrl+Shift+Space"`, `model="gemini-2.5-flash"`, `pinned=True`, etc.).
   - Atomic saving to `%APPDATA%\Peachy\settings.json` via temp file + `os.replace`.
   - Automatic recovery: missing file uses defaults; corrupt file creates `.json.bak` and falls back to defaults without crashing. API keys are never stored here.
5. **Win32 Layer (`core/win32.py`)**:
   - Strict `ctypes` bindings for `RegisterHotKey`, `UnregisterHotKey`, `GetForegroundWindow`, and `SetForegroundWindow` with `argtypes`, `restype`, and `GetLastError` error reporting.
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

### Verified by Automated Tests (31/31 passed)
- **`tests/test_hotkey_parser.py`**:
  - Valid shortcuts parsed: `Ctrl+Shift+Space`, `Alt+Q`, `Win+Shift+S`, `ctrl + alt + f12`.
  - Invalid shortcuts rejected: empty strings, modifiers only, multiple non-modifiers, unknown tokens.
- **`tests/test_settings.py`**:
  - Default values.
  - Save/load round-trip.
  - Missing file fallback.
  - Corrupt JSON recovery with `.bak` file generation.
  - Non-dict JSON recovery.
  - Atomic save leaves no `.tmp` file.
  - Forward-compatible unknown field handling.
- **`tests/test_state_manager.py`**:
  - Happy path lifecycle transitions (`IDLE` -> `CAPTURING` -> `SELECTING` -> `ASKING` -> `THINKING` -> `ANSWERING` -> `IDLE`).
  - Error state and retry transitions.
  - Invalid transitions rejected.
  - Duplicate activation ignored when state is not `IDLE`.
  - Forced reset to `IDLE`.
- **`tests/test_hotkey_manager.py`**:
  - Registration success with Win32 mocked.
  - Registration collision failure path cleanly handled with signal emitted.
  - Hotkey pause/resume toggling OS registration.
  - Hotkey triggering signal dispatched when active and suppressed when paused.
- **`tests/test_app.py`**:
  - Redaction filter strips Gemini API keys (`AIza...`) and secret tokens from logs.

### Needs Manual Check (Checklist for Tanay)
- [ ] Run `python app.py`: icon appears in system tray (pink sparkle), no terminal errors.
- [ ] With another app focused (e.g., Notepad), press `Ctrl+Shift+Space`: tray notification "activated" appears and nothing is typed into Notepad.
- [ ] Hold or spam `Ctrl+Shift+Space`: triggers only once; duplicate spam is ignored.
- [ ] Right-click tray icon -> check "Pause Hotkey": pressing `Ctrl+Shift+Space` does nothing. Uncheck "Pause Hotkey": hotkey works again.
- [ ] Launch a second instance (`python app.py` in another terminal): second instance exits immediately with message, and the existing instance opens the Settings placeholder.
- [ ] Right-click tray icon -> click "Quit": hotkey unregisters, process terminates, zero python processes left in Task Manager.

### Known Bugs
- None.
