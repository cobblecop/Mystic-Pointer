# Mystic Pointer

An open-source, screen-aware AI assistant for your desktop. Select any region and ask a vision model about it, without leaving your workflow.

Inspired by the **Magic Pointer** functionality on **Googlebooks**.

**Supported platforms:** Linux (X11 and Wayland) and Windows 10/11.

---

## Features

- **Flexible selection** — Click a detected image or drag any region. Hold `Ctrl` to select multiple areas.
- **AI panel** — Ask questions and stream responses from Gemini, OpenAI-compatible endpoints, local Ollama, or offline demo mode.
- **Selection actions** — Save screenshots, copy selected areas as separate images, or merge them into one image.
- **Text extraction** — Ask the model to extract text from the current selection.
- **Wayland-native capture** — Uses GNOME Shell or `xdg-desktop-portal` for silent screenshots.
- **Native integration** — System tray, global shortcut support, and an Adwaita-style Preferences window.
- **Quick activation** — Cursor wiggle on X11 and Windows, or a configurable global shortcut.

---

## Install

### One-line install

**Linux (X11/Wayland):**

```bash
curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/install.sh | bash
```

**Windows 10/11 (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/install.ps1 | iex
```

Both installers require Python 3.10+. They create a user-local environment, add a launcher, and register an app-menu or Start-menu entry. Administrator access is not required.

### One-line uninstall

**Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.sh | bash
```

**Windows 10/11 (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.ps1 | iex
```

Configuration and API keys are preserved by default. To remove them as well:

```bash
curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.sh | bash -s -- --purge
```

```powershell
$env:MYSTIC_POINTER_PURGE="1"; irm https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.ps1 | iex
```

Saved screenshots are never deleted. The URLs above use `your-username/mystic-pointer`; replace this with the published repository.

### From source

```bash
git clone https://github.com/your-username/mystic-pointer.git
cd mystic-pointer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

./run.sh
```

On Windows, use `.venv\Scripts\activate` and run `python main.py`.

---

## Setup

1. Start Mystic Pointer from your app menu or with `mystic-pointer`.
2. Open **Preferences → AI Providers**.
3. Choose a provider, enter the required credentials, and save.

For Gemini, you can also set `GEMINI_API_KEY` before launching. The model dropdown lists the vision-capable models available to the selected provider.

---

## Usage

| Action | How |
| :--- | :--- |
| **Activate** | Click the tray icon, use `Ctrl+Alt+G`, or wiggle the cursor on X11/Windows |
| **Select** | Click an image or drag a region; hold `Ctrl` for multiple selections |
| **Ask** | Type a question or choose a suggestion chip |
| **Dismiss** | Press `Escape` or click the dimmed background |

---

## Platform notes

- **Linux (Wayland):** Screenshots use GNOME Shell or `xdg-desktop-portal` with a backend such as `xdg-desktop-portal-gnome`, `xdg-desktop-portal-kde`, or `xdg-desktop-portal-wlr`. Install global shortcuts from the tray menu; cursor wiggle is unavailable.
- **Linux (X11) and Windows:** Cursor wiggle and direct screen capture are available.

---

## License

MIT License. See [LICENSE](LICENSE).
