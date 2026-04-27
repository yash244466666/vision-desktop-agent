#!/usr/bin/env python3
"""
VISION HANDS v3 — Human-like desktop automation using xdotool.
- Uses DBus GNOME Shell extension for screenshots (Wayland).
- Human-like Bézier mouse movements.
- xdotool for keyboard and mouse.
"""

import os, sys, re, subprocess, random, time, math, json

DISPLAY = os.environ.get("DISPLAY", ":0")
SCREEN_W, SCREEN_H = 1920, 1080


def _gnome_shell_screenshot(path="/tmp/vision_screen.png"):
    """Use built-in org.gnome.Shell.Screenshot DBus (requires unsafe mode)."""
    try:
        result = subprocess.run([
            "gdbus", "call", "--session",
            "--dest", "org.gnome.Shell",
            "--object-path", "/org/gnome/Shell/Screenshot",
            "--method", "org.gnome.Shell.Screenshot.Screenshot",
            "false", "false", path
        ], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and os.path.exists(path):
            from PIL import Image
            img = Image.open(path)
            print(f"[Hands] GNOME Shell screenshot: {img.size[0]}x{img.size[1]}")
            return img
        return None
    except Exception:
        return None


def _hermes_extension_screenshot(path="/tmp/vision_screen.png"):
    """Use custom GNOME Shell extension org.hermes.Screenshot.Capture."""
    try:
        result = subprocess.run([
            "gdbus", "call", "--session",
            "--dest", "org.hermes.Screenshot",
            "--object-path", "/org/hermes/Screenshot",
            "--method", "org.hermes.Screenshot.Capture",
            path
        ], capture_output=True, text=True, timeout=10)
        if "true" in result.stdout.lower() or os.path.exists(path):
            from PIL import Image
            img = Image.open(path)
            print(f"[Hands] Hermes extension screenshot: {img.size[0]}x{img.size[1]}")
            return img
        return None
    except Exception:
        return None


def dbus_screenshot(path="/tmp/vision_screen.png"):
    """Take screenshot via DBus."""
    img = _gnome_shell_screenshot(path)
    if img is not None: return img
    img = _hermes_extension_screenshot(path)
    if img is not None: return img
    return None


def fallback_screenshot(path="/tmp/vision_screen.png"):
    """Last resort: try gnome-screenshot or scrot."""
    for cmd in [
        ["gnome-screenshot", "-f", path],
        ["scrot", path],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=5,
                             env={**os.environ, "DISPLAY": DISPLAY})
            if r.returncode == 0 and os.path.exists(path):
                from PIL import Image
                img = Image.open(path)
                arr = __import__('numpy').array(img)
                if arr.mean() < 5:
                    os.unlink(path)
                    continue
                return img
        except Exception:
            continue
    return None


def take_screenshot(path="/tmp/vision_screen.png"):
    """Best-effort screenshot: DBus extension first, fallbacks second."""
    img = dbus_screenshot(path)
    if img is not None: return img
    return fallback_screenshot(path)


# ── Mouse: Human-like Movement ───────────────

def _bezier(ctrl_pts, steps=40):
    pts = []
    for t_idx in range(steps + 1):
        t = t_idx / steps
        x = (1-t)**3 * ctrl_pts[0][0] + 3*(1-t)**2*t * ctrl_pts[1][0] + 3*(1-t)*t**2 * ctrl_pts[2][0] + t**3 * ctrl_pts[3][0]
        y = (1-t)**3 * ctrl_pts[0][1] + 3*(1-t)**2*t * ctrl_pts[1][1] + 3*(1-t)*t**2 * ctrl_pts[2][1] + t**3 * ctrl_pts[3][1]
        pts.append((int(x), int(y)))
    return pts


def _jitter(val, sigma=2):
    return max(0, int(random.gauss(val, sigma)))


def _wobble(pts, amp=0.4):
    result = [pts[0]]
    for i in range(1, len(pts)):
        px, py = result[-1]
        dx = pts[i][0] - px
        dy = pts[i][1] - py
        dist = max(1, math.hypot(dx, dy))
        n = max(1, int(dist / 4))
        for j in range(1, n + 1):
            frac = j / n
            x = px + dx * frac
            y = py + dy * frac
            if dist > 3:
                nx, ny = -dy/dist, dx/dist
                off = random.gauss(0, amp * math.sin(frac * math.pi))
                x += nx * off
                y += ny * off
            result.append((_jitter(x), _jitter(y)))
    return result


def move_mouse(x, y, human=True, duration=0.3):
    x, y = int(x), int(y)
    x = max(0, min(SCREEN_W - 1, x))
    y = max(0, min(SCREEN_H - 1, y))
    pos = get_mouse_pos()
    if pos == (x, y): return
    if not human:
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], env={**os.environ, "DISPLAY": DISPLAY})
        return
    sx, sy = pos
    cx = (sx + x) / 2 + random.randint(-80, 80)
    cy = (sy + y) / 2 + random.randint(-60, 60)
    c1x = sx + (cx - sx) * random.uniform(0.2, 0.5) + random.randint(-20, 20)
    c1y = sy + (cy - sy) * random.uniform(0.2, 0.5) + random.randint(-20, 20)
    c2x = cx + (x - cx) * random.uniform(0.5, 0.8) + random.randint(-20, 20)
    c2y = cy + (y - cy) * random.uniform(0.5, 0.8) + random.randint(-20, 20)
    ctrl = [(sx, sy), (c1x, c1y), (c2x, c2y), (x, y)]
    keyframes = _bezier(ctrl, steps=max(8, int(math.hypot(x-sx, y-sy) / 25)))
    path = _wobble(keyframes, amp=random.uniform(0.2, 0.6))
    step_duration = duration / max(len(path), 1)
    for px, py in path:
        subprocess.run(["xdotool", "mousemove", str(px), str(py)], env={**os.environ, "DISPLAY": DISPLAY})
        time.sleep(step_duration + random.gauss(0, 0.002))


def get_mouse_pos():
    try:
        r = subprocess.run(["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True, env={**os.environ, "DISPLAY": DISPLAY})
        pos = {}
        for line in r.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                pos[k] = int(v)
        return (pos.get("X", 0), pos.get("Y", 0))
    except Exception:
        return (SCREEN_W // 2, SCREEN_H // 2)


def click(x, y, button=1, human=True, duration=0.3):
    move_mouse(x, y, human=human, duration=duration)
    time.sleep(random.uniform(0.04, 0.12))
    subprocess.run(["xdotool", "click", str(button)], env={**os.environ, "DISPLAY": DISPLAY})
    time.sleep(random.uniform(0.05, 0.15))


def double_click(x, y, human=True):
    move_mouse(x, y, human=human)
    subprocess.run(["xdotool", "click", "--repeat", "2", "--delay", "200", "1"], env={**os.environ, "DISPLAY": DISPLAY})


def right_click(x, y, human=True):
    click(x, y, button=3, human=human)


def type_text(text, delay_range=(0.02, 0.08)):
    subprocess.run(["xdotool", "type", "--delay", "40", text], env={**os.environ, "DISPLAY": DISPLAY})


def press_key(key_combo):
    keys = key_combo.replace("+", " + ").split()
    for k in keys:
        subprocess.run(["xdotool", "keydown", k.strip()], env={**os.environ, "DISPLAY": DISPLAY})
        time.sleep(random.uniform(0.01, 0.04))
    for k in reversed(keys):
        subprocess.run(["xdotool", "keyup", k.strip()], env={**os.environ, "DISPLAY": DISPLAY})
        time.sleep(random.uniform(0.01, 0.03))


def scroll(x, y, clicks=3, direction="down"):
    move_mouse(x, y, human=True)
    button = 4 if direction == "up" else 5
    for _ in range(clicks):
        subprocess.run(["xdotool", "click", str(button)], env={**os.environ, "DISPLAY": DISPLAY})
        time.sleep(random.uniform(0.04, 0.12))


def drag(from_x, from_y, to_x, to_y, duration=0.5, button=1):
    move_mouse(from_x, from_y, human=True)
    subprocess.run(["xdotool", "mousedown", str(button)], env={**os.environ, "DISPLAY": DISPLAY})
    move_mouse(to_x, to_y, human=True, duration=duration)
    subprocess.run(["xdotool", "mouseup", str(button)], env={**os.environ, "DISPLAY": DISPLAY})


# ── Parse Actions from LLM ──────────────────

def parse_and_execute(text):
    actions = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("ACTION:"):
            actions.append(line[7:].strip())
    if not actions: return []
    executed = []
    for action in actions:
        parts = action.split()
        cmd = parts[0].lower() if parts else ""
        try:
            if cmd == "click" and len(parts) >= 3:
                click(int(parts[1]), int(parts[2]))
                executed.append(f"click({parts[1]}, {parts[2]})")
            elif cmd == "double_click" and len(parts) >= 3:
                double_click(int(parts[1]), int(parts[2]))
            elif cmd == "right_click" and len(parts) >= 3:
                right_click(int(parts[1]), int(parts[2]))
            elif cmd == "type" and len(parts) >= 2:
                txt = " ".join(parts[1:])
                type_text(txt)
                executed.append(f"type('{txt}')")
            elif cmd == "key" and len(parts) >= 2:
                press_key(parts[1])
                executed.append(f"key({parts[1]})")
            elif cmd == "scroll" and len(parts) >= 2:
                d = parts[1] if parts[1] in ("up", "down") else "down"
                c = int(parts[2]) if len(parts) >= 3 else 3
                mx, my = get_mouse_pos()
                scroll(mx, my, c, d)
            elif cmd == "drag" and len(parts) >= 5:
                drag(int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
            elif cmd == "wait" and len(parts) >= 2:
                time.sleep(float(parts[1]))
            elif cmd == "screenshot":
                executed.append("screenshot(requested)")
            else:
                executed.append(f"unknown({action})")
        except Exception as e:
            executed.append(f"error({action}): {e}")
    return executed


if __name__ == '__main__':
    img = take_screenshot()
    print(f"[Hands] Screenshot: {'OK ' + str(img.size) if img else 'FAILED'}")