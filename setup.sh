#!/usr/bin/env bash
#
# Vision Desktop Agent — One-shot setup script
# Run: chmod +x setup.sh && ./setup.sh
#
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# ── 1. System Dependencies ─────────────────
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq xdotool gnome-shell-extension-tool curl python3-pip 2>/dev/null || {
  warn "apt install had issues — some packages may already be installed"
}

# ── 2. Python Dependencies ─────────────────
info "Installing Python packages..."
pip3 install Pillow numpy 2>/dev/null || pip install Pillow numpy

info "Installing optional packages (OCR + template matching)..."
pip3 install easyocr opencv-python-headless 2>/dev/null || {
  warn "Optional packages failed — OCR/template matching won't work"
  warn "Install them manually: pip3 install easyocr opencv-python-headless"
}

# ── 3. Install GNOME Shell Extension ────────
info "Installing GNOME Shell extension..."
EXT_DIR="${HOME}/.local/share/gnome-shell/extensions/screenshotService@hermes"
mkdir -p "${EXT_DIR}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SCRIPT_DIR}/gnome-shell-extension/extension.js" "${EXT_DIR}/extension.js"
cp "${SCRIPT_DIR}/gnome-shell-extension/metadata.json" "${EXT_DIR}/metadata.json"

# Add to enabled extensions
current=$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || echo "[]")
if echo "$current" | grep -q "screenshotService@hermes"; then
  info "Extension already in enabled-extensions list"
else
  # Add the extension UUID to the list
  new_list=$(echo "$current" | python3 -c "
import sys, json
current = json.loads(sys.stdin.read().replace("'", '""))
if 'screenshotService@hermes' not in current:
    current.append('screenshotService@hermes')
print(json.dumps(current))
" 2>/dev/null || echo "$current")
  gsettings set org.gnome.shell enabled-extensions "$new_list" 2>/dev/null || {
    warn "Could not auto-enable extension. Enable manually after login."
  }
  info "Extension added to enabled-extensions"
fi

# ── 4. API Key Setup ─────────────────────────
AUTH_FILE="${HOME}/.hermes/auth.json"
if [ -f "$AUTH_FILE" ]; then
  # Check if ollama-cloud key exists
  if python3 -c "import json; d=json.load(open('$AUTH_FILE')); d['credential_pool']['ollama-cloud'][0]['access_token']" 2>/dev/null; then
    info "Ollama Cloud API key found in ~/.hermes/auth.json"
  else
    warn "No ollama-cloud key in ~/.hermes/auth.json"
    warn "Set it manually or export OLLAMA_CLOUD_KEY=your-key"
  fi
else
  warn "~/.hermes/auth.json not found"
  warn "Create it with your Ollama Cloud API key, or set OLLAMA_CLOUD_KEY env var"
fi

# ── 5. Xhost Permission ─────────────────────
info "Granting xhost permission for xdotool..."
xhost +local: 2>/dev/null || warn "xhost failed — xdotool may not work"

# ── 6. Verify ───────────────────────────────
info "Verifying installation..."

# Check xdotool
if command -v xdotool &>/dev/null; then
  info "xdotool: $(xdotool version 2>/dev/null || echo 'installed')"
else
  fail "xdotool not found!"
fi

# Check Python modules
python3 -c "from PIL import Image; import numpy; print('PIL + numpy OK')" || fail "Python deps missing!"

# Check extension
if [ -d "${EXT_DIR}" ]; then
  info "Extension files installed at ${EXT_DIR}"
else
  fail "Extension not installed!"
fi

# Test DBus (extension needs logout/login first)
info "Testing DBus connection (extension must be loaded)..."
result=$(gdbus call --session --dest org.hermes.Screenshot \
  --object-path /org/hermes/Screenshot \
  --method org.hermes.Screenshot.Ping 2>/dev/null || echo "FAILED")

if echo "$result" | grep -q "pong"; then
  info "DBus Ping: SUCCESS — extension is running!"
else
  warn "DBus Ping: FAILED — extension not yet loaded"
  warn "Log out and log back in to activate the GNOME Shell extension."
  warn "After login, verify with: gnome-extensions info screenshotService@hermes"
fi

# ── Done ────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  🤖 Vision Desktop Agent — Setup Complete!"
echo "══════════════════════════════════════════════"
echo ""
if echo "$result" | grep -q "pong"; then
  echo "  Test it now:"
  echo "    cd ${SCRIPT_DIR}"
  echo "    python3 vision_brain.py \"Open Firefox\""
else
  echo "  ⚠  LOG OUT AND LOG BACK IN first, then test:"
  echo "    cd ${SCRIPT_DIR}"
  echo "    python3 vision_brain.py \"Open Firefox\""
fi
echo ""
echo "  Interactive mode (chat-style):"
echo "    python3 vision_brain.py -i"
echo ""