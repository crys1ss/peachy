# Midnight Peachy: Redesign Brief

This is the master spec for turning Peachy from a hotkey popup into a full desktop AI assistant. Every Antigravity task in this redesign starts by reading this file, `RULES.md`, `docs/ARCHITECTURE.md` and `docs/PROGRESS.md`. If this file and `RULES.md` disagree, `RULES.md` wins on process (tests, secrets, threading, Win32), this file wins on product and design.

Two agents work in parallel:

- **Track A, "UI" (Antigravity IDE):** owns `ui/`, `resources/`, `scripts/` screenshot and gallery tools, and the UI tests.
- **Track B, "Core" (Antigravity 2.0):** owns `ai/`, `core/`, `history/`, `config/`, `app.py` (except where a step says otherwise), `Peachy.spec`, `requirements*.txt`, and the tests for those.

Neither track edits the other track's files. Where they meet, they meet at the contracts in section 7. If a track needs something across the line, it writes it in its handoff note and the owner adds it in the next step.

---

## 1. What exists today (inspected on main at 4a498ac)

Read the code yourself before changing anything. This is the map, not a substitute.

| Area | Files | What it does now |
|---|---|---|
| Entry point | `app.py` | `PeachyApp` builds everything: `StateManager`, `TrayManager`, `HotkeyManager`, `DoubleTapHook`, `OverlayManager`, `PeachyPopup`, `HistoryStore`, `HistoryWindow`, `AppController`, `SettingsWindow`. Single-instance guard over `QLocalServer`. Redacting rotating log. |
| State machine | `core/state_manager.py` | `IDLE → CAPTURING → SELECTING → ASKING → THINKING → ANSWERING / ERROR → IDLE`. Governs the screenshot flow only. |
| Controller | `core/app_controller.py` | Hotkey → capture → crop → popup ask → `GeminiWorker` (QThread) → answer. Follow-ups keep `types.Content` history in memory. 45 s hard timeout. Saves turns to history on a `HistoryDbWorker` thread when `save_history` is on. `continue_conversation()` reloads the last 20 text messages. Currently writes raw SQL for saves (being moved into the store in PCH-102). |
| AI | `ai/provider.py`, `ai/gemini_provider.py` | `BaseAIProvider.ask(image_png, question, history, answer_length) -> AnswerResult`. `google-genai` `generate_content` (blocking, no streaming), AFC off, 12 s per attempt, fallback chain `FALLBACK_MODELS`, typed errors (`MissingKey`, `InvalidKey`, `RateLimited`, `Timeout`, `Network`, `Blocked`, `EmptyResponse`, `Unknown`). System prompt is tuned for screenshots ("ultra-direct screen utility"). |
| History | `history/store.py`, `history/worker.py` | SQLite at `%APPDATA%\Peachy\history.db`, schema v1: `conversations(id, title, created_at, updated_at, thumbnail)`, `messages(id, conversation_id, role, text, created_at, has_image)`. WAL, corrupt-DB recovery with `.bak`, temp fallback with `is_fallback`. `generate_title()`, `create_thumbnail()`, search, delete, clear, `export_markdown()`. **Images are not stored**, only a `has_image` flag. |
| Settings | `config/settings.py`, `config/key_storage.py` | Dataclass in `%APPDATA%\Peachy\settings.json`, atomic writes, corrupt-file recovery. API key in Windows Credential Manager via `keyring`. Has `theme`, `reduce_motion`, `sound_enabled`, `sound_volume`. `save_history` defaults to **False** (privacy opt-in). |
| Capture | `capture/` | Pixel-exact multi-monitor, mixed-DPI capture. Rectangle and freehand selection overlay. **Do not touch** beyond adding an "attach mode" hook in step 3B. |
| Win32 | `core/win32.py` | All ctypes calls, with argtypes, restype and error checks. Any new Win32 call goes here. |
| UI | `ui/peachy_popup.py` | Frameless `Qt.Tool` popup, `QStackedWidget` with Ask, Thinking, Answer and Error views, pill minimise, pin, `WA_ShowWithoutActivating`, markdown via `QTextBrowser.setMarkdown` and Pygments HTML (`ui/components/code_highlighter.py`). |
| | `ui/history_window.py` | `QDialog` with a `QTreeWidget` list and a transcript pane. **Replaced** by the main window in this redesign. |
| | `ui/settings_window.py` | One long scrolling `QDialog`. **Rebuilt** as categories. |
| | `ui/theme.py` | `ThemeTokens`, `MIDNIGHT_THEME`, `LIGHT_THEME`, QSS generator, Inter font loader. |
| | `ui/components/` | `BrandOrb`, `icons.py` (inline SVG), `code_highlighter.py`, `StreamThrottler`, `Toast`. |
| | `ui/sound.py` | `SoundManager` (QSoundEffect + winsound), 150 ms rate limit. |
| Packaging | `Peachy.spec`, `build.ps1`, `installer/` | PyInstaller onedir, bundles `resources/`. |

### Must keep working (regression list)

1. Global hotkey (default `Ctrl+Shift+Space`) and optional double-tap C, both pausable from the tray.
2. Frozen multi-monitor, mixed-DPI capture with rectangle and freehand selection.
3. Popup that never steals focus when an answer arrives, plus pin, drag, minimise to pill, `Esc` to dismiss.
4. Follow-ups, New Screenshot inside a conversation, Short/Detailed length chip, Retry on error.
5. Every typed provider error shows a friendly message. The 45 s hard timeout still fires. Model fallback still works.
6. API key only in Credential Manager. Logs never contain keys, prompts, image bytes or screenshots.
7. History recovery, `.bak` backups and temp fallback from PCH-101.
8. Single instance. Second launch opens the app instead of starting a second copy.
9. Settings survive restarts, and a corrupt settings file never crashes startup.
10. The PyInstaller build still runs on a clean Windows machine.

### Known gaps found during inspection

- `pygments` is used by `code_highlighter.py` but is **not in `requirements.txt`**, so frozen builds silently lose highlighting.
- `app.py` `_on_settings_applied` calls `history_window.apply_theme()`, which does not exist. The exception is swallowed, so pin, length and **hotkey re-registration are skipped** after saving settings.
- `get_theme()` is called without `settings.theme`, so the theme setting is ignored.
- `get_sound_manager()` is never given settings, so mute and volume are ignored.
- The screenshot system prompt is wrong for a general chat window.

---

## 2. Product shape

Peachy becomes **two surfaces sharing one brain**:

1. **Quick Overlay** (the existing popup, restyled). Hotkey, snip, ask, answer, gone. Stays tiny, fast and polite. Gains an **"Open in Peachy"** action that continues the conversation in the main window.
2. **Peachy main window** (new). A real resizable app with a sidebar of conversations and a full chat view. It opens from the tray, from `Ctrl+Shift+H` (renamed "Open Peachy"), from a second app launch, and from "Open in Peachy".

Both read and write the same `HistoryStore`, use the same provider, and follow the same settings and theme. Closing the main window hides it to the tray. Quit stays in the tray menu.

**Not a rewrite.** The FSM, capture, hotkeys, provider error mapping, key storage and history recovery stay as they are. New code goes beside them.

---

## 3. Visual direction

Midnight Peachy is near-black and quiet, with warm light coming from one place at a time. Think of a dark room with one lamp on. Colour is spent only on the thing you should look at next: the send button, the active conversation, the focused field, Peachy's name.

### 3.1 Colour tokens (Midnight)

Keep the existing `ThemeTokens` field names where they exist, and add the new ones. All text pairs below were contrast-checked.

| Token | Value | Use |
|---|---|---|
| `background` | `#0B0B10` | Window canvas, chat area |
| `secondary` | `#111118` | Sidebar, code block background |
| `surface` | `#171720` | Cards, assistant blocks, composer |
| `elevated` | `#1E1E29` | Menus, palette, toasts, user bubble |
| `hover` | `#23232F` | Row and button hover |
| `border` | `#292735` | Card and input borders |
| `hairline` | `rgba(255,255,255,0.06)` | Dividers |
| `text` | `#F6F3FA` | Primary text |
| `text_secondary` | `#A6A1B3` | Labels, metadata (7.1:1 on surface) |
| `text_tertiary` | `#8F8A9C` | Placeholders, disabled (5.3:1 on surface) |
| `accent` | `#FF9E7D` | **Primary accent, peach.** Focus ring, active marker, links, Peachy name (9.8:1 on background) |
| `accent_2` | `#FF7A90` | Coral rose. Second gradient stop and badges only |
| `accent_ink` | `#1A0F0C` | Text and icons on peach fills (9.3:1) |
| `accent_soft` | `rgba(255,158,125,0.12)` | Selected chips, active row tint |
| `glow` | `rgba(255,158,125,0.22)` | Focus glow, orb halo |
| `success` | `#79E2B5` | Online dot, "Copied" |
| `error` | `#FF647C` | Errors |
| `lavender` | `#B9A4FF` | Code types only (syntax) |

**Gradient rule:** there is exactly one gradient, `accent → accent_2` at 135°. It is used only on the send button, the brand orb and the 2 px active-conversation marker. Nothing else gets a gradient.

**Glass rule:** only the command palette and toasts get translucency (`elevated` at 92% opacity over a 1 px `hairline` border). On Windows 11 the main window may use the Mica backdrop (section 6.4). Nothing else is glass.

**Glow rule:** glow means focus or "Peachy is working". It is never decoration. It's a 0–12 px blur `QGraphicsDropShadowEffect` in `glow`, on one element at a time.

**Accent options** (Settings → Appearance): Peach `#FF9E7D` (default), Coral `#FF8A8A`, Rose `#FF7AB6`, Lavender `#B9A4FF`. The accent swaps `accent`, `glow` and `accent_soft`. Each one is at least 7:1 on `surface`.

**Light theme** keeps the same structure: background `#FBF8F6`, secondary `#F4EFEC`, surface `#FFFFFF`, elevated `#FFFFFF` with a shadow, border `#E9E1DC`, text `#1F1A1D`, text_secondary `#6B6B76`, text_tertiary `#76767F`, accent `#B4472A` for text and focus (5.4:1 on white) and `#FF9E7D` for fills.

### 3.2 Typography

Inter Variable (bundled) for everything, then Segoe UI Variable. Cascadia Code, then Consolas, for code. The `font_scale` setting (90 / 100 / 110 / 125 %) multiplies every size below.

| Role | px | Weight | Line height |
|---|---|---|---|
| Greeting | 26 | 600 | 32 |
| Window/section title | 15 | 600 | 20 |
| Body / messages | 14 | 400 | 22 |
| Composer | 14 | 400 | 20 |
| Sidebar row title | 13 | 500 | 18 |
| Label / chip | 12 | 500 | 16 |
| Metadata / timestamp | 11 | 400 | 14 |
| Code | 13 | 400 | 20 |

### 3.3 Space, radius, icons

- 4 px grid. Paddings used: 4, 8, 12, 16, 20, 24, 32.
- Radii: window 12, cards and messages 14, inputs and buttons 10, chips 8, pills fully round.
- Icons: 1.5 px stroke, 16 px in rows and 18 px in the toolbar, drawn in `ui/components/icons.py` (inline SVG, recoloured at runtime). No emoji in chrome.
- One brand mark, the `BrandOrb`, with a peach-to-rose gradient and a slow 4 s breathing halo only while Peachy is generating.

---

## 4. Main window layout and component hierarchy

```
MainWindow (QMainWindow, min 760×520, default 1100×720, geometry remembered)
├── Sidebar (QFrame, 264 px expanded / 64 px collapsed)
│   ├── BrandHeader: BrandOrb + "peachy" wordmark + collapse button
│   ├── NewChatButton (Ctrl+N)
│   ├── SearchField (Ctrl+F): filters as you type, 150 ms debounce, Esc clears
│   ├── ConversationList (QListView + ConversationDelegate, custom painted)
│   │   ├── Section "Pinned"
│   │   ├── Section "Today" / "Yesterday" / "Previous 7 days" / "Previous 30 days" / "<Month Year>"
│   │   └── Row: title (1 line, elided), preview (1 line, text_tertiary), relative time; hover shows ⋯ menu
│   └── SidebarFooter: profile chip (display name + status dot) · Settings gear
├── ChatArea (QStackedWidget)
│   ├── WelcomeView
│   │   ├── BrandOrb (48 px)
│   │   ├── Greeting: "Good evening, <name>" (time-of-day aware; no name → "Good evening")
│   │   ├── Subline: "Ask anything, or snip your screen with Ctrl+Shift+Space"
│   │   ├── 4 suggestion cards (2×2): "Explain a screenshot", "Debug this error", "Summarise a page", "Draft a reply"
│   │   └── Composer (centred, 680 px max)
│   └── ConversationView
│       ├── ChatHeader: title (double-click to rename) · model chip · status pill · ⋯ (pin, rename, export, delete)
│       ├── MessageList (QScrollArea, 760 px max content width, centred)
│       │   ├── DaySeparator
│       │   ├── UserMessage: right-aligned, elevated fill, radius 14 with a 4 px bottom-right corner, image thumbnails above text; hover shows edit · copy · time
│       │   ├── AssistantMessage: no bubble. Full-width block with a small orb and "Peachy" in accent, markdown body, code blocks with language label and copy; footer shows copy · regenerate · time · model
│       │   ├── ThinkingIndicator: orb breathing + 3 dots, "Thinking…" → "Writing…" when the first chunk lands
│       │   └── ErrorBlock: inline, error icon, friendly message, Retry
│       ├── JumpToLatest pill (appears when scrolled up during streaming)
│       └── Composer
└── Overlays (children of MainWindow, not separate windows)
    ├── CommandPalette (Ctrl+K)
    ├── ShortcutSheet (Ctrl+/)
    ├── Toast host (bottom centre)
    └── SettingsView (slides over ChatArea; not a separate dialog)
```

**Why assistant replies have no bubble:** long markdown and code in a bubble feels cramped and generic. A plain block with a small header reads like a document, while user turns stay as compact bubbles. This is the biggest single "not a generic chatbot" decision.

### Composer

- `QPlainTextEdit` subclass. 44 px tall for one line, grows to 200 px (about 8 lines), then scrolls.
- `Enter` sends, `Shift+Enter` adds a newline, and `Up` in an empty composer edits your last message.
- Left side: attach button (paperclip), with a menu for "Upload image…", "Snip screen" (uses the capture flow in attach mode) and "Paste" (`Ctrl+V` also pastes images directly).
- Attachments show as 56 px thumbnails above the text with an × to remove. Up to 4 images, PNG/JPEG/WebP, each 20 MB or less.
- Right side: Short/Detailed chip, then send. Send is a 32 px gradient circle that is disabled (flat `hover`) when empty, and becomes a stop square while generating.
- Focus: 1 px border goes `border → accent` and the glow fades in (section 5).
- Drag and drop an image file onto the window to attach it.

### Settings (slides in over the chat, `Ctrl+,`)

Left rail of categories, with the content on the right. Every change saves at once (atomic `save_settings`). There is no Save button, and a toast confirms anything that needs a restart.

| Category | Contents |
|---|---|
| General | Display name · Launch at startup · Close button hides to tray · Popup position · Sound on/off, volume slider, "Play test sound" |
| Appearance | Theme cards Midnight / Light / System with live mini previews · Accent swatches · Font size 90–125 % · Reduce motion (shows "Windows animations are off" when the OS setting is off) |
| AI & Models | API key (masked, Test, status) · Model dropdown (from the API, with a static fallback) · Default answer length · Fallback models on/off |
| Keyboard Shortcuts | Recorders for the Capture and Open Peachy global hotkeys · Double-tap C · read-only table of in-app shortcuts |
| Privacy & Data | Save chat history · Save screenshots with chats · Storage location and size · Export all (Markdown/JSON) · Clear all history (confirm) · Privacy statement |
| About | Version from `version_info.txt` · Model status · Open logs folder · Licences (Inter OFL) |

### Command palette (`Ctrl+K`)

Centred 560 px card, 20% from the top, with a search field and a list of actions plus matching conversations. Arrows move, Enter runs, Esc closes. Actions: New chat, Snip screen, Search chats, Toggle sidebar, Settings sections, Switch theme, Change model, Export chat, Shortcut reference, Quit.

### In-app shortcuts

| Keys | Action |
|---|---|
| Ctrl+N | New chat |
| Ctrl+K | Command palette |
| Ctrl+F | Search conversations |
| Ctrl+B | Toggle sidebar |
| Ctrl+, | Settings |
| Ctrl+/ | Shortcut reference |
| Ctrl+Shift+C | Copy last answer |
| Ctrl+R | Regenerate last answer |
| Esc | Stop generating / close overlay / clear search |
| Ctrl+↑ / Ctrl+↓ | Previous / next conversation |
| Ctrl+V | Paste text or image |

The global hotkeys stay as they are: `Ctrl+Shift+Space` capture and `Ctrl+Shift+H` "Open Peachy".

---

## 5. Motion

Everything goes through `ui/motion.py`:

```python
def should_animate(settings) -> bool:      # False if settings.reduce_motion or Windows animations are off
def duration(ms: int) -> int:              # 0 when should_animate() is False
def fade(widget, start, end, ms, curve)    # QGraphicsOpacityEffect, removed when done
def slide(widget, prop, start, end, ms, curve)
```

Rules:

- Nothing over 240 ms except the breathing halo. Exits are about 30% faster than entrances.
- Animate `pos`, `maximumWidth` and opacity only. Never animate layout of the message list.
- Remove every `QGraphicsOpacityEffect` when its animation ends. Effects on large `QTextBrowser`s kill frame rate and nested effects break painting.
- Only messages that **arrive** animate. Opening an old chat renders instantly.
- With reduce motion on, everything snaps (0 ms), but colour/hover changes still apply.

| What | Duration | Curve | Behaviour |
|---|---|---|---|
| App launch | 220 ms | OutCubic | Window opacity 0→1 and content 8 px up, sidebar rows stagger 15 ms (first 8 only) |
| Welcome | 260 ms | OutCubic | Orb scales 0.9→1, greeting fades in, cards stagger 40 ms |
| Sidebar collapse/expand | 200 ms | InOutCubic | `maximumWidth` 264↔64, labels fade out in the first 80 ms and in during the last 80 ms |
| Chat switch | 140 ms | OutQuad | Old content fades to 0 over 60 ms, new fades in, scroll to bottom without animation |
| Message enter | 180 ms | OutCubic | Opacity 0→1, 8 px up |
| Streaming text | n/a | n/a | Re-render every 60 ms via `StreamThrottler`, caret block blinks at 530 ms at the end of the text |
| Thinking dots | 900 ms loop | Sine | 3 dots, 150 ms phase offset, timer stops when hidden |
| Hover | 120 ms | OutQuad | Background `transparent → hover` |
| Press | 80 ms | OutQuad | Scale to 0.97 (via a geometry inset), back on release |
| Focus glow | 160 ms | OutCubic | Blur 0→12, border colour to accent |
| Menus / dropdowns | 140 ms | OutCubic | Opacity and 4 px down, origin at the anchor |
| Settings | 200 ms | OutCubic | Slides in from the right 24 px with a fade, chat dims to 60% |
| Palette | 160 ms | OutBack (amplitude 1.2) | Scale 0.98→1 and fade, background dims |
| Toast | 180 in / 140 out | OutCubic | 12 px up and fade, auto-hides after 1.8 s, pauses on hover |
| Smooth scroll | 200 ms | OutCubic | `QPropertyAnimation` on the scrollbar value for keyboard/jump scrolls only |

Performance target: 60 fps on a 1080p laptop iGPU. Measure with `scripts/perf_probe.py` (step 5A). Fewer than 2 dropped frames per sidebar toggle, and keystroke-to-paint in the composer under 16 ms during streaming.

---

## 6. Technical approach

### 6.1 Chat flow (main window), separate from the capture FSM

The FSM stays in charge of the screenshot flow only. The main window gets its own controller, `core/chat_session.py`, so typing in the main window can never block or corrupt the hotkey flow.

```
Composer.send ─▶ ChatSession.send(text, images)
                 ├─ persist user message + attachments (HistoryDbWorker)
                 ├─ StreamWorker(QThread) ─▶ provider.ask_stream(...)
                 │     chunk ─▶ stream_chunk(req_id, text_so_far)   (throttled in UI)
                 │     done  ─▶ stream_finished(req_id, message)   (persisted, then emitted)
                 │     error ─▶ stream_failed(req_id, kind, message)
                 └─ stale request ids are ignored (same pattern as GeminiWorker)
```

### 6.2 Streaming

`GeminiProvider.ask_stream()` uses `client.models.generate_content_stream()` with the same config, fallback chain and error mapping as `ask()`.

- A fallback is allowed only **before the first chunk**. After text has been shown, an error ends the stream with what was received plus an inline error and Retry.
- Usage metadata (prompt and output token counts) from the final chunk is returned for the status tooltip.
- The 45 s hard timeout becomes "no chunk for 20 s" for streams.
- `ask()` stays for the popup until step 3B switches the popup to streaming too.

### 6.3 History schema v2

Migration runs in `HistoryStore._init_db()` inside one transaction, after copying `history.db` to `history.v1.bak`. It's idempotent and tested from a real v1 file.

```sql
ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN title_locked INTEGER NOT NULL DEFAULT 0;  -- user renamed it
ALTER TABLE conversations ADD COLUMN source TEXT NOT NULL DEFAULT 'overlay';   -- 'overlay' | 'chat'
ALTER TABLE messages ADD COLUMN model TEXT;
ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'complete';       -- 'complete' | 'error' | 'stopped'
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    mime TEXT NOT NULL,
    width INTEGER, height INTEGER,
    data BLOB,            -- NULL when "Save screenshots with chats" is off
    thumb BLOB NOT NULL,  -- 256 px PNG, always kept so the transcript still shows something
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);
CREATE INDEX IF NOT EXISTS idx_conversations_pinned ON conversations(pinned DESC, updated_at DESC);
```

**Context restore:** reopening a chat rebuilds provider history from all messages, capped at the last 40 turns or about 60k characters. Images are re-sent only for the latest user turn that still has `data`. Older images go as the text "[image omitted]".

**Titles:** use `generate_title()` immediately, then after the first answer an off-thread short Gemini call asks for a 3–6 word title. It never overwrites a `title_locked` title, and if it fails the heuristic title stays.

**Privacy:** `save_history` stays opt-in. The first time the main window opens, the Welcome view shows one dismissible card: "Keep your chats? Peachy can save conversations on this PC so you can come back to them." with Keep chats / Not now. With history off, the sidebar shows the current session only, plus a small "History is off" link to Privacy settings.

### 6.4 Windows integration (all in `core/win32.py`)

- `set_dark_title_bar(hwnd, dark)`: `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE=20)`.
- `set_backdrop(hwnd, kind)`: `DWMWA_SYSTEMBACKDROP_TYPE=38` (Mica=2) on Windows 11 22H2+, silently skipped elsewhere.
- Use a native title bar (keeps Snap Layouts, Aero Shake and accessibility) and colour it to match. **Do not build a frameless main window.**

### 6.5 Rendering

- Message bodies use `QTextBrowser` with the existing `render_markdown_html()` (Pygments). The height fits the document and the browser's own scrollbars are off.
- Code blocks get a header row (language label · Copy) as an HTML table row with an anchor link `peachy://copy/<n>`, handled in `anchorClicked`.
- Streaming re-renders the whole message every 60 ms. Above 20k characters this switches to 150 ms (`# ponytail:` note about incremental rendering).
- Message list: a `QScrollArea` with a `QVBoxLayout` of message widgets. It loads the newest 40 and adds older ones in pages of 40 when you scroll near the top, keeping the scroll position.

### 6.6 Status and errors

- `ChatSession.status_changed` emits `ready | busy | offline | invalid_key | rate_limited | no_key`. It's derived from the last request and is never polled.
- The status pill (header and profile chip) shows a coloured dot, and its tooltip shows the model, last latency and today's token count (in memory only).
- Each error kind maps to a message and an action: no_key → "Add API key" (opens AI settings), invalid_key → same, rate_limited → Retry, offline → Retry, blocked → Rephrase, empty → Retry.

### 6.7 Dependencies

Add only `pygments` (already used, missing from requirements). Do **not** add `qframelesswindow`, `qfluentwidgets`, a markdown library or a web view. PySide6 can do all of this.

---

## 7. Contracts between tracks

Track B implements these exactly. Track A codes against them, using `tests/fakes/fake_chat_session.py` until B's version lands.

```python
# core/chat_session.py  (Track B)
class ChatSession(QObject):
    conversation_started = Signal(int, str)        # conv_id, title
    conversation_loaded  = Signal(int, list)       # conv_id, [MessageDict]
    title_changed        = Signal(int, str)
    message_added        = Signal(dict)            # MessageDict (user message, persisted)
    stream_started       = Signal(int)             # request_id
    stream_chunk         = Signal(int, str)        # request_id, full text so far
    stream_finished      = Signal(int, dict)       # request_id, MessageDict (assistant)
    stream_failed        = Signal(int, str, str)   # request_id, error_kind, friendly message
    conversations_changed = Signal()
    status_changed       = Signal(str)

    current_conversation_id: Optional[int]
    def new_chat(self) -> None
    def load(self, conv_id: int) -> None
    def send(self, text: str, images: list[bytes] = ()) -> None
    def regenerate(self) -> None                      # replaces the last assistant message
    def edit_and_resend(self, message_id: int, text: str) -> None  # drops later messages, resends
    def stop(self) -> None
    def set_answer_length(self, length: str) -> None

# MessageDict
{"id": int, "conversation_id": int, "role": "user"|"model", "text": str,
 "created_at": str, "model": str|None, "status": "complete"|"error"|"stopped",
 "attachments": [{"id": int, "mime": str, "thumb": bytes, "has_full": bool}]}

# history/store.py additions  (Track B)
rename_conversation(conv_id, title) -> None          # sets title_locked=1
set_pinned(conv_id, pinned: bool) -> None
list_conversations(query=None) -> [ {id, title, updated_at, pinned, preview, source} ]
save_exchange(...)                                   # from PCH-102
add_attachment(message_id, mime, data|None, thumb, w, h) -> int
get_attachment_data(attachment_id) -> bytes|None
delete_messages_from(conv_id, message_id) -> None    # inclusive, for edit/regenerate

# history/grouping.py  (Track B, pure function)
group_conversations(rows, now: datetime) -> list[tuple[str, list[dict]]]
# order: "Pinned", "Today", "Yesterday", "Previous 7 days", "Previous 30 days", then "October 2026"…

# core/app_controller.py additions  (Track B)
open_in_main_window = Signal(int)                    # conv_id, emitted by popup action
attachment_captured = Signal(bytes)                  # PNG from capture in attach mode
def capture_for_attachment(self) -> None

# config/settings.py additions  (Track B)
display_name: str = ""
accent: str = "peach"            # peach | coral | rose | lavender
font_scale: int = 100            # 90 | 100 | 110 | 125
sidebar_collapsed: bool = False
main_window_geometry: str = ""   # base64 of QWidget.saveGeometry()
close_to_tray: bool = True
fallback_models_enabled: bool = True
```

---

## 8. Project structure (target)

```
ai/            provider.py (+ask_stream), gemini_provider.py (+streaming, chat system prompt, list_models)
core/          app_controller.py, chat_session.py (new), stream_worker.py (new), state_manager.py, win32.py, ...
history/       store.py (v2), grouping.py (new), worker.py
config/        settings.py (+fields)
ui/
  main_window.py          (new) shell, sidebar ↔ chat wiring, shortcuts
  sidebar.py              (new) brand header, search, ConversationList + delegate
  chat_view.py            (new) header, message list, jump-to-latest
  messages.py             (new) UserMessage, AssistantMessage, ThinkingIndicator, ErrorBlock
  composer.py             (new) auto-growing input, attachments, send/stop
  welcome_view.py         (new)
  settings_view.py        (new) replaces settings_window.py content; old dialog removed in step 4A
  command_palette.py      (new)
  shortcut_sheet.py       (new)
  motion.py               (new)
  theme.py                tokens, accents, font scale, QSS
  peachy_popup.py         restyled overlay (kept)
  history_window.py       removed in step 3A after the sidebar replaces it
  components/             brand_orb, icons, code_highlighter, throttle, toast, toggle_switch (new), chip (new)
tests/
  fakes/fake_chat_session.py, fakes/fake_provider.py (new)
scripts/
  component_gallery.py (new), perf_probe.py (new), generate_screens.py (update)
```

---

## 9. Testing and debugging checklist

Every step: `python -m pytest -q` with real output pasted into the handoff. A step with any failing or skipped test does not count as finished.

**Automated (must exist by the end):**
- Schema v1→v2 migration from a real v1 fixture, re-run idempotent, `.v1.bak` created.
- `group_conversations` edges: midnight boundary, pinned + today, empty list, month rollover.
- `ChatSession` with `FakeProvider`: send, stream order, stop mid-stream (status `stopped` persisted), regenerate replaces only the last answer, edit-and-resend drops later messages, stale request id ignored, every error kind → correct `stream_failed` kind.
- Streaming fallback only before the first chunk.
- Context restore cap (40 turns / 60k chars) and image omission.
- Settings round-trip for every new field, plus unknown values clamped to defaults.
- Composer: Enter sends, Shift+Enter newlines, Up edits last, 4-attachment limit, size limit.
- Sidebar: search filters, rename persists, pin moves to Pinned, delete removes and selects a neighbour.
- `should_animate()` false → all durations 0.
- Theme: every text/background token pair ≥ 4.5:1 (test computes contrast).
- Popup regression: focus not stolen (`WA_ShowWithoutActivating` still set), pill, pin.

**Manual (Zidane runs on Windows, the agent lists these in every handoff):**
- [ ] 100%, 125% and 150% scaling, and two monitors with different scaling.
- [ ] Hotkey capture → popup → "Open in Peachy" continues the same chat in the main window.
- [ ] Quit and relaunch: chats, pins, titles, theme, accent, font size and window size are all back.
- [ ] Pull the network mid-stream: partial text is kept, an inline error shows, and Retry works.
- [ ] Wrong API key: friendly error with a button to settings.
- [ ] Windows "Animation effects" off: no animations anywhere.
- [ ] Sidebar toggle and streaming feel smooth (no visible stutter).
- [ ] Packaged build (`build.ps1`) runs on a clean user profile, with fonts, sounds and syntax colours present.

**Debugging aids:** `PEACHY_HISTORY_DB_PATH` for throwaway DBs, `PEACHY_MODEL` to force a model, `scripts/component_gallery.py` to view every component in both themes without an API key, `--fake-provider` flag (step 2B) to run the whole app against `FakeProvider`.

---

## 10. Definition of done

Peachy is finished when:

1. You can press the hotkey, snip, get an answer in under 2 s to the first token, and keep typing in your other app throughout.
2. You can open Peachy from the tray, see "Good evening, Zidane", click a suggestion, and watch a streamed, highlighted answer appear smoothly.
3. Every conversation, from either surface, is in the sidebar grouped by date, searchable, renameable, pinnable, deletable and exportable, and is all still there after a reboot.
4. Reopening a chat lets you continue it with context.
5. You can edit a past message or regenerate an answer, and the transcript stays consistent after a restart.
6. Settings has six tidy categories, every change sticks, and nothing needs a Save button.
7. With animations on, everything moves briefly and smoothly. With them off, nothing moves.
8. No error ever shows a traceback. Every failure has a human sentence and a next action.
9. All tests pass, the manual checklist is ticked, the packaged build works, `README.md` screenshots show Midnight Peachy, and `docs/PROGRESS.md` is current.

---

## 11. Handoff note format (end of every step, both tracks)

Append to `docs/handoffs/<task-id>.md`:

```
## <task-id> – <title>
Branch: agy/<task-id>-<slug>   Commits: <hashes>
Done: …
Contract changes: none | <exact signatures added/changed>
Tests: <paste the final pytest summary line>
Manual checks for Zidane: …
Known issues / follow-ups: …
```

Push the branch, do **not** merge. Claude reviews the branch on GitHub, and Zidane merges after approval.
