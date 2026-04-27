# 🤖 Vision Desktop Agent

**Autonomous vision-driven desktop agent for Linux (GNOME/Wayland).**

Sees the screen → Thinks with cloud vision AI → Acts with human-like mouse/keyboard → Loops until done.

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   EYES      │────▶│     BRAIN       │────▶│     HANDS        │
│ Screenshot   │     │ kimi-k2.6       │     │ xdotool          │
│ via DBus     │     │ Cloud Vision    │     │ Bézier mouse     │
│ Extension    │     │ Action Parser    │     │ Human-like delay │
└─────────────┘     └─────────────────┘     └──────────────────┘
       ▲                                            │
       └──────────────── loop ──────────────────────┘
```

## Why This Exists

On GNOME Wayland, **every standard screenshot method produces a black frame**: MSS, scrot, ImageMagick, pyautogui, gnome-screenshot, XDG Portal — all fail. The XDG Portal denies non-sandboxed apps, and GNOME Shell's `Eval()` is blocked without unsafe mode.

The **only** reliable way to capture the screen is from **inside the GNOME compositor** itself. This project ships a custom GNOME Shell Extension that exposes a DBus method (`org.hermes.Screenshot.Capture`) which uses the `Shell.Screenshot` API with a `GOutputStream` — the correct GNOME 49 API.

Combine that with a cloud vision LLM (kimi-k2.6) and human-like Bézier mouse movements, and you get an agent that can autonomously operate your desktop.

---

## Architecture

| Component | File | Purpose |
|-----------|------|---------|
| **Brain** | `vision_brain.py` | Main agent loop — screenshot → LLM → parse → execute → repeat |
| **Eyes** | `vision_eyes.py` | Cloud vision API client (kimi-k2.6), OCR text finder, OpenCV template matching |
| **Hands** | `vision_hands.py` | DBus screenshots, Bézier mouse, xdotool keyboard, action parser |
| **Extension** | `gnome-shell-extension/extension.js` | GNOME Shell extension — DBus `org.hermes.Screenshot` service |
| **Setup** | `setup.sh` | One-shot installer for all dependencies |

### The Agent Loop

1. **Screenshot** — Call `org.hermes.Screenshot.Capture` via DBus → save PNG
2. **See** — Send screenshot + prompt to kimi-k2.6 cloud vision model
3. **Think** — LLM returns structured `ACTION:` commands (click, type, key, scroll, drag...)
4. **Act** — Parse and execute each action via xdotool with human-like timing
5. **Wait** — Pause for UI to respond, then loop back to step 1
6. **Done** — LLM outputs `ACTION: done` when task is complete

### Why Each Decision

| Decision | Reason |
|----------|--------|
| Cloud vision (not local) | kimi-k2.6 has far superior screen understanding vs Moondream/tiny local models |
| Ollama Cloud API | OpenAI-compatible endpoint, uses existing API key infrastructure |
| GNOME Shell Extension | Only way to screenshot on Wayland — X11/Portal methods all return black frames |
| `GOutputStream` (not boolean) | GNOME 49 changed `Shell.Screenshot` — 2nd arg is now a stream, not a flash flag |
| `register_object` with 5 args | GJS 1.88 requires exactly: (path, iface_info, method_call, get_property, set_property) |
| xdotool | Works on Wayland with `xhost +local:` — pyautogui also works but xdotool is more reliable |
| Bézier mouse paths | Human-like movement avoids detection by anti-bot systems |

---

## Quick Start

### Prerequisites

- **GNOME 49** on Wayland (tested on Ubuntu 25.04+ / GNOME 49.4)
- **Python 3.10+**
- **Ollama Cloud API key** (or any OpenAI-compatible vision API)
- **xdotool** installed
- **Logout/login** required after extension install

### 1. Clone & Run Setup

```bash
git clone https://github.com/yash244466666/vision-desktop-agent.git
cd vision-desktop-agent
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Install `xdotool`, `curl`, Python packages
- Copy the GNOME Shell extension to `~/.local/share/gnome-shell/extensions/`
- Add the extension to GNOME's enabled-extensions list
- Verify the DBus connection

### 2. Log Out and Log Back In

The GNOME Shell extension only loads on session start. **You must log out and log back in** (not just lock screen — full logout).

After login, verify:
```bash
gnome-extensions info screenshotService@hermes
```

Should show: `State: ACTIVE`

### 3. Test the Extension

```bash
# Health check
gdbus call --session \
  --dest org.hermes.Screenshot \
  --object-path /org/hermes/Screenshot \
  --method org.hermes.Screenshot.Ping
# Expected: ('pong',)

# Take a screenshot
gdbus call --session \
  --dest org.hermes.Screenshot \
  --object-path /org/hermes/Screenshot \
  --method org.hermes.Screenshot.Capture \
  /tmp/test_screenshot.png
# Expected: (true, 'Screenshot saved to /tmp/test_screenshot.png')
```

### 4. Configure API Key

The agent loads the Ollama Cloud API key from `~/.hermes/auth.json`:

```json
{
  "credential_pool": {
    "ollama-cloud": [
      {
        "access_token": "your-api-key-here"
      }
    ]
  }
}
```

Or set the environment variable:
```bash
export OLLAMA_CLOUD_KEY="your-api-key-here"
```

### 5. Run the Agent

```bash
# Single task mode
python3 vision_brain.py "Open Firefox and search for weather"

# With custom steps/delay
python3 vision_brain.py "Open Settings" --steps 15 --delay 3.0

# Interactive chat mode
python3 vision_brain.py -i
```

---

## Action Reference

The LLM outputs structured `ACTION:` lines. The parser in `vision_hands.py` handles:

| Action | Syntax | Example |
|--------|--------|---------|
| Click | `ACTION: click X Y` | `ACTION: click 450 300` |
| Double-click | `ACTION: double_click X Y` | `ACTION: double_click 960 540` |
| Right-click | `ACTION: right_click X Y` | `ACTION: right_click 100 200` |
| Type text | `ACTION: type text here` | `ACTION: type Hello World` |
| Key combo | `ACTION: key combo` | `ACTION: key ctrl+c` |
| Scroll | `ACTION: scroll direction N` | `ACTION: scroll down 3` |
| Drag | `ACTION: drag X1 Y1 X2 Y2` | `ACTION: drag 100 200 400 500` |
| Wait | `ACTION: wait N` | `ACTION: wait 2` |
| Re-screenshot | `ACTION: screenshot` | Take fresh screenshot before continuing |
| Done | `ACTION: done message` | `ACTION: done Opened Firefox` |

### Coordinate System

- Top-left: `(0, 0)`
- Bottom-right: `(1919, 1079)` on 1920×1080
- Y increases downward

---

## GNOME Shell Extension Details

### DBus Interface

```
Name:       org.hermes.Screenshot
Path:       /org/hermes/Screenshot
Methods:
  Ping()                                    → (s:reply)
  Capture(s:filepath)                       → (b:success, s:info)
```

### GNOME 49 Shell.Screenshot API

The critical API call inside the extension:

```javascript
// CORRECT for GNOME 49:
global.screenshot.screenshot(include_cursor, GOutputStream, callback);

// WRONG (old API, will fail with "Expected GOutputStream"):
global.screenshot.screenshot(include_cursor, flash_bool, callback);
```

To create the `GOutputStream`:
```javascript
let file = Gio.File.new_for_path(filePath);
let stream = file.replace(null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
```

### register_object (GJS 1.88)

GJS 1.88 requires **exactly 5 arguments** for `register_object`:

```javascript
connection.register_object(
  object_path,        // string: '/org/hermes/Screenshot'
  interface_info,     // Gio.DBusInterfaceInfo
  method_call_handler, // function
  null,               // get_property handler (not needed)
  null                // set_property handler (not needed)
);
```

**The 3-arg and 6-arg versions both fail.**

### ⚠️ Critical Pitfalls

| Pitfall | Details |
|---------|---------|
| **Never call `UninstallExtension`** | The DBus method **deletes extension files from disk**. Use `gnome-extensions disable` instead. |
| **Logout/login required** | GNOME Shell caches extension code. Disable/enable doesn't reload — only a new session works. |
| **Register inside `bus_acquired`** | The DBus connection must be ready before `register_object`. Register inside the `on_bus_acquired` callback. |
| **`Clutter.Rect` not a constructor** | In GNOME 49, `Clutter.Rect` is not a constructor — don't use it. |
| **`Gdk.Display.get_default()` returns null** | Inside extensions, this returns null. Use `global.display` instead. |
| **`unsafe_mode_enabled` chicken-and-egg** | Even when dconf shows `true`, `Shell.Eval` still returns `(false, '')`. Our extension bypasses this entirely. |

---

## Using with Different Vision Models

The agent uses the OpenAI-compatible chat completions API. You can swap models:

### Change model in `vision_brain.py`

```python
brain = VisionBrain(task="...", max_steps=30)
brain.eyes = VisionEyes(model="qwen3-vl:235b-instruct")
```

### Use a different API endpoint

Edit `vision_eyes.py`:

```python
OLLAMA_CLOUD_URL = "https://api.openai.com/v1/chat/completions"
# And update the auth header accordingly
```

### Supported models (tested)

| Model | Endpoint | Notes |
|-------|----------|-------|
| `kimi-k2.6` | Ollama Cloud | ✅ Best screen understanding |
| `kimi-k2.5` | Ollama Cloud | ✅ Good, but k2.6 is better |
| `qwen3-vl:235b-instruct` | Ollama Cloud | ✅ Strong vision, larger |
| Any OpenAI-compatible vision model | Any endpoint | Should work if it supports `image_url` |

---

## How to Use on a Fresh Machine

```bash
# 1. Clone
git clone https://github.com/yash244466666/vision-desktop-agent.git
cd vision-desktop-agent

# 2. Setup (installs everything)
chmod +x setup.sh && ./setup.sh

# 3. Logout + Login
# ... log out, log back in ...

# 4. Verify extension
gnome-extensions info screenshotService@hermes
# Should show: State: ACTIVE

# 5. Test Ping
gdbus call --session \
  --dest org.hermes.Screenshot \
  --object-path /org/hermes/Screenshot \
  --method org.hermes.Screenshot.Ping
# Expected: ('pong',)

# 6. Set up API key
mkdir -p ~/.hermes
echo '{"credential_pool":{"ollama-cloud":[{"access_token":"YOUR-KEY"}]}}' > ~/.hermes/auth.json

# 7. Run!
python3 vision_brain.py "Open Firefox and go to github.com"
```

---

## Troubleshooting

### Screenshot returns black image

You're probably not using the GNOME Shell extension. Check:
```bash
gnome-extensions info screenshotService@hermes
```
If not ACTIVE, logout/login. If that doesn't help, check `journalctl -f -o cat /usr/bin/gnome-shell` for errors.

### DBus method not found

```bash
# Check if the name is owned on the session bus
gdbus introspect --session --dest org.hermes.Screenshot --object-path /org/hermes/Screenshot
```
If it says "no such name", the extension isn't loaded.

### xdotool not working

On Wayland, xdotool needs X11 compatibility:
```bash
xhost +local:
export DISPLAY=:0
```

Add `xhost +local:` to your startup applications for persistence.

### Vision model not responding

Check your API key:
```bash
# Quick test
curl -s https://ollama.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR-KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-k2.6","messages":[{"role":"user","content":"hello"}]}'
```

---

## File Structure

```
vision-desktop-agent/
├── vision_brain.py           # Main agent loop (Eyes → Brain → Hands)
├── vision_eyes.py            # Cloud vision client + OCR + template matching
├── vision_hands.py           # Screenshot, Bézier mouse, xdotool, action parser
├── gnome-shell-extension/
│   ├── extension.js          # GNOME Shell DBus screenshot service
│   └── metadata.json         # Extension metadata (GNOME 49)
├── setup.sh                  # One-shot installer
├── requirements.txt          # Python dependencies
├── .gitignore
└── README.md                 # This file
```

---

## License

MIT — do whatever you want with it.

## Credits

- **GNOME Shell extension** — the only Wayland screenshot method that actually works
- **kimi-k2.6** — Moonshot AI's vision model via [Ollama Cloud](https://ollama.com)
- **Bézier mouse paths** — because automation should look human
- **xdotool** — the OG Linux input automation tool