# Peachy Build Plan for Antigravity

Oct 22, 2026 · @Aurex Marketing

## Fix these before you start

Five things in the original idea will cause bugs or impossible promises. The daily prompts below already handle all of them.

1. **Double tap C fires while you type.** Words like accept, success, occur and account contain "cc". Also, the first C is already typed into your app before Peachy knows it was a double tap. So the default shortcut is Ctrl+Shift+Space, and double tap C stays an optional setting with strict rules (both taps within about 280 ms, no other key between, no modifiers held). Test it on Day 5 and decide if you keep it.
2. **Windows cannot be paused.** The "paused" feeling comes from showing a frozen screenshot full screen. Apps keep running underneath (a video keeps playing). This is how every snipping tool works, and it is enough.
3. **There are two different Gemini models.** Gemini 3.8 Flash inside Antigravity writes your code. Peachy itself needs its own API key from Google AI Studio and a vision model name. Never let the agent guess that model name from memory; the Day 3 prompt makes it list the models your key can actually use.
4. **The agent cannot press your hotkey or drag on your screen.** It can run unit tests, but overlay, focus, DPI and multi monitor behaviour can only be tested by you. Each day ends with a manual checklist. Do not start the next day until it passes.
5. **"Perfect, no errors" needs a safety net.** Commit to git at the end of every good day. If the agent breaks something, you roll back instead of debugging for hours.

## Set up Antigravity once (Thursday, 30 minutes)

Do this before the Day 1 prompt. It keeps the agent on track for all six days.

1. Install Python 3.12 from python.org (tick "Add to PATH") and Git.
2. Get a Gemini API key at aistudio.google.com. In a terminal run `setx GEMINI_API_KEY "your_key"`, then close and reopen Antigravity.
3. Make a folder `peachy`, run `git init` inside it, open it in Antigravity.
4. Save your full master prompt (the spec you wrote) as `docs/SPEC.md`.
5. Save the rules below as `RULES.md` in the project root. If your Antigravity version supports workspace rules, add it there too; otherwise every daily prompt already tells the agent to read it.
6. For each day's main prompt use **Planning** mode, not Fast. Read the plan it proposes before approving. Reject any plan that skips tests or says "placeholder".
7. Start a **new agent conversation each day** with the Resume prompt (last section), then paste that day's prompt.
8. If your Antigravity plan offers a stronger reasoning model than Flash, switch to it for Day 2 (DPI math) and the keyboard hook on Day 5. Those are the two places Flash models most often loop.
9. End each day with `git add .` and `git commit -m "Day N done"`.

**RULES.md** (paste exactly):

```markdown
# Peachy agent rules
- The spec is docs/SPEC.md. Progress is docs/PROGRESS.md. Read both before any work.
- Target: Windows 10/11, Python 3.12, PySide6. A real desktop app. No web, no Electron.
- Work only on today's stage. Do not refactor or rewrite working modules unless I ask.
- Never replace working code with placeholders, TODO stubs or fake logic in production code.
- Never hardcode API keys. Never log screenshots, image bytes, keys or prompt text.
- Never guess library APIs. Check the official docs (PySide6, google-genai, Pillow, mss, keyring, PyInstaller) and name the page you used.
- All network and slow work runs off the UI thread (QThread or QRunnable with signals).
- All Win32 calls live in core/win32.py, via ctypes, with argtypes, restype and error checks.
- After every change: run `python -m pytest -q`, paste the real output, fix failures, rerun.
- Never say "works" or "tested" for anything you did not actually run. List what I must test manually.
- End every session by updating docs/PROGRESS.md: done, verified by tests, needs manual check, known bugs.
```

## Schedule: working MVP Saturday, finished Tuesday

The full loop (hotkey, select, ask, answer) works by Saturday night with plain styling. Sunday and Monday make it cute and unbreakable; Tuesday packages it and is your buffer.

| Day | Date | What gets built | Done when |
| --- | --- | --- | --- |
| 1 | Thu 22 Oct | Plan, skeleton, tray, settings file, global hotkey, state machine | Hotkey from Notepad fires once, tray Quit exits cleanly |
| 2 | Fri 23 Oct | Screen capture, frozen selection overlay, multi monitor and DPI | The saved crop matches exactly what you drew; Esc returns you to your app |
| 3 | Sat 24 Oct | Gemini provider, ask view, workers, end to end MVP | You select an MCQ and get the right answer |
| 4 | Sun 25 Oct | Cute pink popup, follow ups, copy, drag, pin, minimize, focus rules | Popup never steals focus and matches your reference look |
| 5 | Mon 26 Oct | Settings window, keyring, double tap C, full error handling, tests | Every failure shows a friendly message; full test suite passes |
| 6 | Tue 27 Oct | PyInstaller build, README, acceptance check, bug bash | Peachy.exe works on a machine without Python |

If Day 2 overruns (it is the hardest day), borrow time from Sunday's polish, never from testing.

## Day 1, Thursday: plan, shell and hotkey

Goal: a tray app with a reliable global hotkey and a state machine that blocks double activation. No capture or AI yet.

```text
Read RULES.md and docs/SPEC.md first. Today is Day 1 of 6: architecture, desktop shell and global hotkey. Do NOT build capture, AI or the popup today.

PART A: PLAN (wait for my approval before writing code)
1. Inspect the workspace and environment (python --version, Windows build).
2. Write docs/ARCHITECTURE.md with: module list; the state machine (IDLE, CAPTURING, SELECTING, ASKING, THINKING, ANSWERING, ERROR) with every allowed transition and what happens on entry and exit; the threading model; and Windows limitations we must design around (UIPI and admin windows, foreground lock rules, mixed DPI monitors, DRM content capturing black).
3. Design decision: use ONE Peachy popup window that switches between Ask, Thinking, Answer and Error views, instead of separate question and answer windows. Fewer focus handoffs, fewer bugs.
4. Choose pinned package versions and name the official doc page you checked for each.

PART B: BUILD (after approval)
1. Skeleton: requirements.txt and requirements-dev.txt (pytest, pytest-qt), .gitignore, .env.example with GEMINI_API_KEY= placeholder only, the module layout from ARCHITECTURE.md, docs/PROGRESS.md.
2. app.py: QApplication with setQuitOnLastWindowClosed(False); single instance guard (a second launch tells the first one to open Settings, then exits); logging to %LOCALAPPDATA%\Peachy\logs with rotation and a redaction helper.
3. config/settings.py: dataclass with defaults, stored at %APPDATA%\Peachy\settings.json, atomic save (temp file + os.replace). Missing or corrupt file: back it up, fall back to defaults, never crash. The API key is never stored here.
4. core/win32.py: ctypes wrappers with argtypes, restype and error checks for RegisterHotKey, UnregisterHotKey, GetForegroundWindow, SetForegroundWindow.
5. core/hotkey_manager.py: register Ctrl+Shift+Space (default) with MOD_NOREPEAT through RegisterHotKey, receive WM_HOTKEY through a QAbstractNativeEventFilter, emit a Qt signal. Parse strings like "Ctrl+Shift+Space" and "Alt+Q". If registration fails, emit a clear error, keep running. Unregister on pause and on quit.
6. core/state_manager.py: explicit state machine that rejects invalid transitions and ignores activation unless state is IDLE, so spamming the hotkey can never open two overlays. Emits state_changed.
7. ui/tray_manager.py: tray icon (pink sparkle drawn with QPainter for now), menu: Ask Peachy, Settings (simple placeholder dialog is fine today), Pause Hotkey (checkable), Quit. Quit unregisters hotkeys, stops threads, exits the process.
8. For today, activation only logs "activated" and shows a tray notification.

TESTS in tests/: shortcut parsing (valid and invalid), settings defaults, save/load round trip, corrupt file recovery, state machine valid and invalid transitions, activation ignored when not IDLE, hotkey registration failure path with win32 mocked.

FINISH: run pytest and paste the real output, update docs/PROGRESS.md, list exactly what I must test by hand.
```

**Your manual check before committing:**

- [ ] `python app.py` starts, the tray icon appears, no errors in the terminal
- [ ] With Notepad focused, Ctrl+Shift+Space shows the notification and types nothing into Notepad
- [ ] Holding the shortcut down triggers only once
- [ ] Pause Hotkey disables it; unpausing brings it back
- [ ] Launching a second copy does not create a second tray icon
- [ ] Quit leaves no python process in Task Manager

## Day 2, Friday: frozen screenshot and selection

Goal: the hotkey freezes the screen, you draw a box, and Peachy gets a pixel exact crop on any monitor at any scaling. This is the hardest day; most bugs in apps like this are DPI math.

```text
Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Today is Day 2 of 6: screen capture and the frozen selection overlay. No AI today.
Flow for today: hotkey -> CAPTURING -> SELECTING -> crop kept in memory -> IDLE. Add a debug switch: if env var PEACHY_DEBUG_SAVE_CROP=1, save the crop PNG to a temp folder so I can check it.

1. capture/screen_capture.py
 - On activation, FIRST store the current foreground HWND so we can restore it later.
 - Capture every monitor once, before any Peachy window is visible. For each monitor return: image in physical pixels, its QScreen, logical geometry, device pixel ratio.
 - Use either QScreen.grabWindow(0) per screen or the mss library. Pick one, justify it, and prove the monitor to QScreen matching is correct with mixed DPI (for example laptop at 150 percent plus external at 100 percent) and negative coordinates (a monitor left of or above the primary).
 - Target under 150 ms for one 1080p screen. Log the timing, never the image.
 - Add scripts/capture_check.py: captures all monitors, prints name, logical geometry, DPR and image size for each, saves PNGs to a temp folder.
2. capture/selection_overlay.py
 - One overlay window PER MONITOR (avoids mixed DPI bugs of one giant window). Frameless, topmost, Qt.Tool so there is no taskbar button, exactly covering that screen, painting that screen's frozen image at the right DPR so it is pixel sharp, never blurry.
 - About 35 percent black dim over everything except the selection. Inside the selection show the original bright image, a 2 px pink border (#F472B6), a light pink tint, and a small label with width x height in physical pixels.
 - Crosshair cursor. Click and drag in any direction. A selection stays on the monitor where the drag started and is clamped to its edges.
 - Keys: Esc cancels on all overlays. Enter confirms. Backspace clears the rectangle. Right click cancels. Mouse release with a valid rectangle confirms.
 - Minimum 8 x 8 physical pixels; anything smaller is ignored and must never trigger a request later.
 - On confirm or cancel: close ALL overlays, restore the normal cursor, release mouse and keyboard grabs, free images not needed, and on cancel restore focus to the saved HWND.
 - The overlay must get keyboard focus so the FIRST Esc press works. Handle the Windows foreground lock (the hotkey press grants us foreground rights; use activateWindow and SetForegroundWindow if needed).
 - Any exception or unexpected close returns to IDLE and cleans up. Safety timeout: no input for 60 seconds cancels.
3. capture/geometry.py: pure functions with no widgets, so they are testable: normalize a rect from any drag direction, clamp to bounds, logical to physical conversion with DPR, crop box from rect.

TESTS: rect normalization for all 4 drag directions, clamping, DPR 1.0 / 1.25 / 1.5 / 2.0, negative monitor origins, tiny selections rejected, cancel returns to IDLE, hotkey during SELECTING ignored. Crop test: a synthetic image with known coloured squares where the crop must match pixel for pixel.

FINISH: pytest output, update PROGRESS.md, list my manual checks.
```

**Your manual check before committing:**

- [ ] Run `scripts/capture_check.py` and open the PNGs: each matches its monitor, sharp, correct size
- [ ] Press the hotkey over a playing YouTube video: the overlay shows a still frame
- [ ] Drag in all 4 directions; the debug crop matches exactly what you boxed
- [ ] The first Esc closes the overlay and you can type in your previous app immediately
- [ ] No Peachy button appears in the taskbar during selection
- [ ] Spam the hotkey 10 times fast: never more than one overlay
- [ ] A 3 x 3 px box does nothing
- [ ] Change Windows scaling (Settings, Display, Scale) to 125 and 150 percent and repeat; with two monitors, test each one

## Day 3, Saturday: Gemini and the working MVP

Goal: the full loop works end to end with plain styling. Tonight is the MVP checkpoint; commit it as a safe restore point.

```text
Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Today is Day 3 of 6: the Gemini provider, the popup's Ask/Thinking/Answer/Error views with PLAIN styling, and the full loop working end to end. Styling is tomorrow.

1. ai/provider.py: an abstract provider interface, ask(image_png or None, question, history) -> AnswerResult, plus typed errors: MissingKey, InvalidKey, RateLimited, Timeout, Network, Blocked, EmptyResponse, Unknown. Each has a short friendly message.
2. ai/gemini_provider.py using the official google-genai SDK (from google import genai). Check the CURRENT SDK docs for: creating the client, sending image bytes plus text in one request, system instructions, request timeouts, chat history, and listing models. Do not write this API from memory.
 - The model name comes from settings; env var PEACHY_MODEL overrides it. Do NOT hardcode a guessed model name. Add scripts/list_models.py that uses my key to print the models that support content generation. I will choose a vision capable Flash model from that list and set it in settings.
 - The API key is read from GEMINI_API_KEY through ONE function (keyring comes on Day 5).
 - Image prep with Pillow: PNG, downscale only if the long side is over 2048 px, never upscale.
 - System instruction: "You are Peachy, a concise screen assistant. Answer the user's question about the image. If there is no question, work out what the content is and give the most useful short response: multiple choice -> the correct option first, then one or two lines why; code or error -> cause and fix; chart or table -> the key takeaway; foreign language -> translation. Be short by default and detailed only when asked. If text is blurry or cut off, say exactly what you cannot read. Never invent text that is not visible. Use simple markdown."
 - Follow ups keep the conversation history, so the image is not resent on every message.
3. core/worker.py: requests run in a QThread worker. Each request has an id; the controller drops any result whose id is not current, so a late reply can never update a closed or newer popup. Cancel marks the request obsolete and returns the UI immediately. One request at a time; Send is disabled while THINKING. Hard timeout 45 s.
4. ui/peachy_popup.py, plain styling today, one window with views:
 - Ask: small thumbnail of the crop, text field focused automatically, Send, Cancel. Enter sends, Esc cancels. An empty question is allowed (auto explain).
 - Thinking: "thinking..." text plus Cancel.
 - Answer: QTextBrowser rendering markdown, Copy, follow up field plus Send, New Screenshot, Close.
 - Error: the friendly message plus Retry.
 - Position: next to the selected region (right, else left, else below), always fully inside that monitor's available area.
5. core/app_controller.py: wires hotkey -> capture -> overlay -> popup -> provider through the state machine. Closing the popup returns to IDLE, frees the image and restores focus to the previous app.

TESTS with a fake provider (no network, no real key): request contains an image part plus the text and the model from settings; SDK exceptions map to our errors; timeout; stale response dropped; double send blocked; missing key shows the MissingKey message; full happy path through the controller with pytest-qt.

THEN ONE REAL CALL: write scripts/smoke_gemini.py that builds a test PNG with Pillow showing the text "2 + 2 = ?", sends it with my key, and prints the answer. Run it and paste the real output, or the real error if it fails.

FINISH: pytest output, smoke test output, update PROGRESS.md, list my manual checks.
```

**Your manual check before committing ("MVP works"):**

- [ ] `scripts/list_models.py` prints models; you pick a vision capable Flash model and put it in settings
- [ ] Box an MCQ on a website: correct option comes back
- [ ] Box a Python error: it explains the fix
- [ ] Box something and send with no question: a useful auto answer
- [ ] A follow up question remembers the context
- [ ] Wi-Fi off: friendly error; Retry works after reconnecting
- [ ] Remove the env var and restart: friendly "add your key" message, no crash
- [ ] Cancel while thinking, take a new screenshot: the old answer never appears

## Day 4, Sunday: the cute popup

Goal: the popup looks like your reference (white card, soft pink, sparkle) and behaves politely: it never steals focus or blocks other apps. Attach your reference screenshot in the Antigravity chat with this prompt.

```text
Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Today is Day 4 of 6: make the popup cute, polished and well behaved. Do not change capture, provider or state logic except to fix bugs, and tell me if you do. The attached image is the look I want.

VISUAL IDENTITY (original design, do not copy any existing product)
 - All tokens in ui/theme.py. Light: accent #F472B6 (hover #EC4899), soft surface #FFF1F6, card #FFFFFF, text #1F1F23, muted #6B6B76, border #F9C9DC. Dark: surface #1E1A1D, card #2A2328, text #F5F0F3, same accent. Follow the Windows light/dark setting.
 - Font Segoe UI Variable, fallback Segoe UI. Body 13 to 14 px, title 15 px semibold.
 - Card: 16 px radius, soft shadow (translucent frameless window with a painted rounded rect), 16 px padding, about 380 px wide, max height 60 percent of the screen, answer area scrolls.
 - Header: sparkle mascot (a simple 4 point star with a small dot, as SVG in resources/), "peachy" in lowercase, subtitle "Screen assistant", icon buttons for pin, minimize, close with tooltips.
 - Ask view: dashed pink outline around the thumbnail, placeholder "Ask about this...", hint "Enter to send, Esc to cancel".
 - Answer view: title "Here's the answer!" on the first answer only; markdown with monospace code blocks on a light pink background; Copy button that shows "Copied" for 1.5 s; rounded pill follow up input with Send; New Screenshot button.
 - A small "Short / Detailed" chip that changes the length instruction for the next request.
 - Animation: 150 to 200 ms fade plus an 8 px slide on show; three bouncing dots while thinking. No animation timers running while hidden.

WINDOW BEHAVIOUR (most important)
 - Frameless, Qt.Tool (no taskbar button). Stays on top only while pinned; pinned is ON by default.
 - The Answer view appears WITHOUT stealing focus (WA_ShowWithoutActivating). The Ask view is the exception: it takes focus so I can type right after selecting.
 - When I click another app it keeps focus normally; Peachy never pulls focus back. Clicking Peachy's input lets me type.
 - Drag by the header to move. Always clamped inside the screen work area, also after a monitor is unplugged or the resolution changes (listen to screen change signals and re-clamp).
 - Minimize collapses to a small pink pill (sparkle + "peachy") that stays on screen; clicking it expands again.
 - New Screenshot hides the popup, runs selection, then continues the SAME conversation with the new image.
 - Close clears the conversation (nothing saved), returns to IDLE and frees memory.
 - Crisp at 100, 125, 150 and 200 percent scaling.

TESTS: views switch correctly; Copy puts the text on the clipboard; position clamping as a pure function; minimize and expand; Close resets the conversation; New Screenshot keeps history (fake provider).
Render each view with fake data using QWidget.grab() and save to docs/screens/ (never real screen content).

FINISH: pytest output, update PROGRESS.md, list my manual checks.
```

**Your manual check before committing:**

- [ ] The images in `docs/screens/` match your reference vibe (if not, send the Bug prompt with what to change)
- [ ] Get an answer, then click into Chrome and type: Chrome keeps focus and the popup stays visible
- [ ] Unpinned, the popup goes behind windows you click
- [ ] Dragging to a screen edge never pushes it off screen
- [ ] Minimize to pill and back works
- [ ] New Screenshot continues the same chat
- [ ] Windows dark mode looks right
- [ ] A long "explain in detail" answer scrolls cleanly

## Day 5, Monday: settings, double tap C, hardening

Goal: everything configurable, the key stored safely, and every failure ends in a friendly message instead of a crash.

```text
Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Today is Day 5 of 6: settings window, secure key storage, optional double tap C, privacy and a hardening pass.

1. ui/settings_window.py in the same Peachy style:
 - Shortcut: a "click, then press keys" recorder. Validate, try to register, show conflicts inline, keep the old shortcut if the new one fails. Applies without restart.
 - Double tap C: OFF by default, interval slider 200 to 500 ms (default 280), warning text "May trigger while typing words with cc".
 - AI: masked API key field with a Test button (small real call, shows success or the real friendly error); model dropdown filled from the models list, with a text field fallback.
 - Popup: pinned by default on/off, position (near selection or last used spot).
 - Launch at startup via winreg at HKCU\Software\Microsoft\Windows\CurrentVersion\Run, quoted exe path, removed when disabled.
 - Privacy text: "Peachy only looks at your screen when you press the shortcut. It sends only the area you select, and only when you press Send. Nothing is recorded or saved."
2. Key storage with keyring (Windows Credential Manager), service name "Peachy". Lookup order: keyring, then GEMINI_API_KEY. Never written to settings.json or logs.
3. core/double_tap.py: a WH_KEYBOARD_LL hook via ctypes, installed only when enabled, removed when disabled, paused or quitting. Rules:
 - the callback returns within a few ms (record a timestamp, post a Qt signal, always CallNextHookEx);
 - never swallow or change keys;
 - ignore injected events (LLKHF_INJECTED) and auto repeat from a held key;
 - count only plain C with no Ctrl, Alt or Win held;
 - fire only on two key downs within the interval with no other key between;
 - keep a strong reference to the callback so Python never garbage collects it.
 Put the detection logic in a pure class that is fed key events, so it is unit testable. Document that keys typed in admin windows are invisible to the hook unless Peachy runs as admin.
4. Hardening pass. For each item, fix it or prove it with a test: missing key; invalid key; rate limit 429 ("Peachy needs a breather, try again in a moment"); timeout; offline; safety blocked response; empty response; tiny selection; monitor plugged or unplugged during selection; scaling changed while running; hotkey conflict; overlay closed by Alt+F4; an exception inside any Qt slot (sys.excepthook plus qInstallMessageHandler -> log, friendly toast, back to IDLE); corrupt settings; quitting while a request runs (thread stops, no crash, no leftover process).
5. Privacy audit: search the codebase and a real log file and prove no image bytes, keys or prompt text are logged; temp files exist only in debug mode and are deleted on exit.

TESTS: settings save and validation (mocked registration); keyring then env lookup order (mocked keyring); double tap logic with fake events: "c c" fast fires, "c c" slow does not, "c x c" does not, "ctrl+c ctrl+c" does not, held c does not, injected does not; startup registry calls mocked; every hardening item that can be unit tested.

FINISH: run the FULL suite, report passed / failed / skipped counts with the real output, update PROGRESS.md, list my manual checks.
```

**Your manual check before committing:**

- [ ] Change the shortcut to Alt+Q in Settings: works immediately, no restart
- [ ] Pick a shortcut another app already uses: friendly conflict message
- [ ] Paste the key, Test passes; delete the env var, restart, still works
- [ ] Turn on double tap C and type "success accept occur" in Notepad. If it triggers too often, leave it off
- [ ] Change scaling or unplug a monitor while Peachy runs: no crash
- [ ] Quit while thinking: no python left in Task Manager
- [ ] Enable startup, sign out and back in: Peachy is in the tray

## Day 6, Tuesday: package, document, accept

Goal: a Peachy.exe that runs on a PC without Python, a README, and an honest acceptance report. No new features today.

```text
Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Today is Day 6 of 6: packaging, documentation and final verification. NO new features.

1. build.ps1: create a clean venv, install pinned dependencies, run pytest and stop if anything fails, then build with PyInstaller in onedir mode, windowed (no console), with an app icon (.ico generated from the sparkle SVG at 16, 32, 48 and 256 px), version info, and all resources. Output: dist\Peachy\Peachy.exe. Explain why onedir instead of onefile (faster start, fewer antivirus false positives).
2. Verify the frozen build: Qt plugins present (platforms, imageformats including svg), same DPI behaviour as from source, single instance guard, logs folder created, keyring backend works inside the exe.
3. Only if time remains: installer/peachy.iss for Inno Setup (Start Menu shortcut, optional startup, uninstall also removes the startup entry).
4. README.md: what Peachy is, screenshots from docs/screens, install, getting a Gemini API key, first run, shortcuts, settings, privacy, troubleshooting (hotkey not working or in conflict, admin windows, DRM video captured black, SmartScreen warning on an unsigned exe, antivirus false positives, where logs are), building from source.
5. docs/ACCEPTANCE.md: go through docs/SPEC.md section by section as a table: requirement | done / partial / not done | how verified (test name, or "manual"). Be honest; partial is fine, a false "done" is not.

FINISH: build output, pytest output, the ACCEPTANCE.md table, and my final manual checklist.
```

**Your final check:**

- [ ] `build.ps1` finishes and creates `dist\Peachy\Peachy.exe`
- [ ] Close Antigravity and double click the exe: the whole flow works
- [ ] Copy the `dist\Peachy` folder to another PC or Windows user without Python: it runs
- [ ] Every "partial" line in ACCEPTANCE.md either gets fixed with the Bug prompt or you accept it
- [ ] Your spec's final acceptance test: from another app, select, ask, get the answer, keep working, quit cleanly
- [ ] `git tag v1.0`

## Reusable prompts

Use these any day. The Resume prompt opens every new session; the others are for when things go wrong.

**Resume (start of every day, before the day prompt):**

```text
New session. Read RULES.md, docs/SPEC.md, docs/ARCHITECTURE.md and docs/PROGRESS.md. Summarize in 5 lines: what works, what is verified by tests, what still needs my manual check, and known bugs. Then run pytest and paste the output. Do not change any code in this reply.
```

**Bug report:**

```text
Bug.
What I did: <steps>
What I expected: <...>
What happened: <...>
Monitors and scaling: <e.g. one laptop screen at 125%>
Log excerpt: <paste the last lines of %LOCALAPPDATA%\Peachy\logs>

First explain the root cause with evidence from the code; do not guess. Write a failing test that reproduces it if possible, then fix it, then run the full suite. Change only what this bug needs.
```

**Proof check (when the agent sounds too confident):**

```text
Before we continue: list every claim you made this session that something works. For each one, show the exact test or command output that proves it, or mark it "unverified, needs manual check". Do not fix anything in this reply.
```

**Unstick (same fix failing 3 times):**

```text
Stop. This fix has failed several times. Show me git diff against the last commit, then revert to it. Propose 2 genuinely different approaches with trade offs, and wait for my choice.
```
