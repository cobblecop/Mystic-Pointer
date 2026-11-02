# Mystic Pointer

> An open-source, cross-platform screen-aware AI assistant inspired by the pointer gesture found on new Chromebooks / Chromebook Plus, bringing multimodal AI directly to your desktop.

Supported OS: **Linux** (X11 & Wayland) & **Windows 10/11**

---

## Features (Recreated from the Chromebook Gesture)

- **Cursor Wiggle Gesture** (X11): Quickly shake/wiggle your cursor left and right for a moment to trigger Mystic Pointer instantly.
- **Configurable Sensitivity**: Adjust wiggle sensitivity from low (harder to trigger) to high (rapid trigger) via a slider in Preferences.
- **Keyboard Shortcut**: `Ctrl+Alt+G` on Windows; on Linux (including Wayland) install a system shortcut from the tray menu.
- **Wayland-native capture**: Uses GNOME Shell's silent screenshot service on GNOME and the `xdg-desktop-portal` API elsewhere, instead of the black frames returned by XWayland tools.
- **System Tray / Status Bar**:
  - Click the tray icon to activate.
  - Quick toggle to **Enabled**.
  - Toggle **Allow cursor wiggle**.
  - One-click **Set Up Ctrl+Alt+G Shortcut** on GNOME (required on Wayland).
- **Seamless Activation**:
  - The captured frame is **paused**, so a playing video cannot move on while you choose an area.
  - The frame and dim layer fade in together and the screen edge glows softly.
  - The prompt panel stays out of the way until you select an image or area, then fades in next to it.
- **Smart Image Hover**:
  - Hover over an image to brighten it through the dimmed overlay. Text, buttons, and UI chrome are ignored.
  - Click an image to lock it in as a selection.
  - Detection favours colour-rich photos and illustrations. Grayscale and very flat images can still be captured with click & drag.
- **Click & Drag Area Selection**:
  - Drag over any custom rectangular area on screen.
- **Multi-Item Selection & Comparison**:
  - Select multiple screen regions by holding **`Ctrl`** while clicking/dragging.
  - Or click the **`+ Add`** button next to thumbnails to append more elements.
- **Floating AI Panel**:
  - A dark, Adwaita-inspired popover that feels native on GNOME.
  - Thumbnail chips for selected screen areas with remove (`×`) buttons.
  - Natural question input: *"Ask about your selection…"*
  - Contextual suggestion chips:
    - Single selection: *Summarize*, *Explain*, *Extract text*, *Translate*, *What is this?*
    - Multiple selections: *Compare items*, *Summarize both*, *Extract text*, *What's the difference?*
  - Real-time streaming responses rendered as clean rich text (headings, lists, code, tables) with one-click **Copy** to clipboard.
  - Drag the header (or empty panel space) to move the dialog anywhere on screen.
- **Native Preferences Window**:
  - A GNOME-style sidebar with card-based preference rows.
  - Custom animated switches, Adwaita light/dark themes, and no web-style toolbars.
  - All provider and gesture settings are organized into General and AI Providers pages.
- **Multi-Provider AI Architecture**:
  - **Gemini API (Recommended)**: Native multimodal support. The model dropdown lists the vision-capable models currently available to your API key, and defaults to the future-proof `gemini-flash-latest` alias.
  - **OpenAI-Compatible & Local Ollama Vision**: Connect to local vision models (e.g., `llama3.2-vision`, `llava`, `minicpm-v`) or OpenAI endpoints. Available vision models are discovered from the endpoint; Ollama's per-model `capabilities` are used when present.
  - **Offline Demo Mode**: Test and preview gestures and UI without requiring an API key.
- **Quick Dismiss**:
  - Press **`Escape`** or click anywhere on the dimmed background to dismiss.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- Linux (Ubuntu/Debian, Fedora, Arch, etc.) or Windows 10/11
- On Wayland: GNOME uses its built-in Shell screenshot service. Other desktops need
  `xdg-desktop-portal` plus a backend (`xdg-desktop-portal-kde` or
  `xdg-desktop-portal-wlr`). The GNOME portal is used as a fallback.
  These are installed by default on GNOME, KDE and most wlroots desktops.

### 2. Installation

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/your-username/mystic-pointer.git
cd mystic-pointer

python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt   # For development / pyright / ruff
```

### 3. Running Mystic Pointer

The repository keeps its environment in `.venv`, so no activation step is needed:

```bash
./run.sh              # start in the system tray
./run.sh --activate   # open Mystic Pointer immediately
```

Equivalently:

```bash
.venv/bin/python main.py
.venv/bin/python main.py --activate
```

On Windows use `.venv\Scripts\python.exe main.py` (or activate the environment
first and run `python main.py`).

The Mystic Pointer icon will appear in your system tray / status bar.

If your desktop does not provide a system tray (some minimal Wayland setups), Mystic
Pointer opens Preferences on launch instead. Bind a system shortcut to
`mystic-pointer --activate` to trigger it; closing the Preferences window exits the app.

---

## Configuration & Gemini Setup

1. Right-click the **Mystic Pointer** tray icon and select **Preferences**.
2. Open the **AI Providers** page.
3. Select **Gemini**.
4. Paste your Gemini API key ([get a free key from Google AI Studio](https://aistudio.google.com/)).
5. Click **Test connection** to verify.
6. Click **Save**.

*(Alternatively, you can set the `GEMINI_API_KEY` environment variable prior to launching).*

### Model discovery

The **Model** dropdown is populated from the provider whenever the Preferences window opens, when the active provider changes, and after a successful connection test. It lists models that can accept image input, not just text-only models.

- **Gemini**: the models returned by `models.list` for your API key are filtered to general-purpose Gemini/Gemma chat models. Gemini's list API does not expose input modalities, so embeddings, TTS, image-generation, live/audio, transcription, and specialised agent models are excluded by name.
- **OpenAI-compatible**: vision-capable families are detected from the `/models` response. Ollama endpoints are detected automatically and each model's `vision` capability is read from `/api/show`.
- Use the **Refresh** button next to the dropdown to refresh the list manually.
- Older saved models remain selectable, but are marked **(legacy)** if they are known to be retired for new Gemini API keys. Models no longer listed by the provider stay available with a "saved model" tooltip. Choose a `-latest` alias if a request reports that your current model is unavailable.

---

## How to Use

| Action | How to Trigger |
| :--- | :--- |
| **Activate (X11/Windows)** | Wiggle mouse left and right rapidly, press `Ctrl+Alt+G`, or click the tray icon |
| **Activate (Wayland)** | Click the tray icon, or set up the system shortcut via the tray menu, then press `Ctrl+Alt+G` |
| **Select Single Image** | Hover over an image and click |
| **Select Custom Area** | Click and drag over the region |
| **Multi-Select** | Hold `Ctrl` while selecting, or click `+ Add` next to a thumbnail |
| **Ask about the selection** | Type your question and press `Enter`, or click a suggestion chip |
| **Exit Overlay** | Press `Escape` or click anywhere on the dimmed screen |

---

## 🖥️ Wayland notes

Wayland deliberately hides the raw screen and global input from applications, which
changes how Mystic Pointer works:

- **Screenshots** on GNOME use the Shell's screenshot service with the flash disabled,
  so activation is silent and there is no screen-cast indicator. KDE and other
  Wayland desktops use `org.freedesktop.portal.Screenshot`. GNOME/KDE show no
  permission dialog for a single screenshot; a capture typically takes about
  0.3–0.6 s on GNOME and can take longer through the portal fallback. Temporary
  screenshots are deleted after they are read. Event sounds are muted during the
  portal fallback so the camera-shutter sound is never played.
- **Global shortcuts** cannot be registered by the app. Use the tray menu item
  **Set Up Ctrl+Alt+G System Shortcut** on GNOME. It adds a standard GNOME custom
  shortcut that runs `mystic-pointer --activate`; a second invocation forwards the
  request to the running tray process (no duplicate app). If an existing shortcut
  was left with an empty command or binding (it looks present but does nothing),
  the tray process repairs it automatically at startup.
- **Wiggle detection** is disabled on Wayland because `QCursor.pos()` only reports
  cursor movement over the app's own windows. The toggle remains available for X11.
- **Multi-monitor**: activation captures and dims the display that currently contains
  the cursor. This avoids the mixed-DPI and window-placement problems that Wayland
  clients cannot solve.
- If activation shows an error instead of the overlay, check that
  `xdg-desktop-portal` is running:

  ```bash
  systemctl --user status xdg-desktop-portal xdg-desktop-portal-gnome
  ```

On Windows and X11 the frozen frame is grabbed directly with Qt and activation is
effectively instant.

---

## 🧪 Development & Quality Checks

Run the linter and type-checker:

```bash
# Code formatting and linting
ruff check mystic_pointer/ tests/
ruff format --check mystic_pointer/ tests/

# Strict type checking
pyright mystic_pointer/

# Unit tests
pytest tests/ -v
```

---

## 📄 License
MIT License.
