#!/usr/bin/env python3
"""
VISION BRAIN v3 — Autonomous vision-driven desktop agent.
- Eyes: kimi-k2.6 cloud vision via Ollama Cloud
- Hands: xdotool + human-like Bézier mouse
- Screenshot: GNOME Shell DBus extension (Wayland-only reliable method)

The agent loop:
  1. Take screenshot via DBus extension
  2. Send to kimi-k2.6 with instruction prompt
  3. Parse structured ACTION commands from response
  4. Execute actions via xdotool
  5. Wait, screenshot again, repeat

Usage:
  python3 vision_brain.py "Open Firefox and search for cats"
  python3 vision_brain.py  # interactive mode
"""

import os, sys, re, json, time, argparse
from datetime import datetime

# Ensure DISPLAY is set
os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":0")
# Xhost for xdotool on Wayland
os.system("xhost +local: > /dev/null 2>&1")

from vision_eyes import VisionEyes
from vision_hands import take_screenshot, parse_and_execute, get_mouse_pos, click, type_text, press_key


# ── System Prompt for Vision Agent ───────────

SYSTEM_PROMPT = """You are a desktop automation agent. You see SCREENSHOTS of a GNOME Linux desktop (1920x1080).
Your job is to look at the screen and output EXACT ACTION commands to complete the user's task.

COORDINATE SYSTEM: Top-left is (0,0), bottom-right is (1919,1079). Y increases downward.

OUTPUT FORMAT — output ONLY action lines, one per line:
  ACTION: click X Y          — Left-click at coordinates
  ACTION: double_click X Y   — Double-click
  ACTION: right_click X Y    — Right-click
  ACTION: type text here     — Type text (spaces allowed)
  ACTION: key ctrl+c         — Press key combo (ctrl, alt, shift, super + key)
  ACTION: scroll down 3      — Scroll (up/down, N clicks)
  ACTION: drag X1 Y1 X2 Y2  — Drag from point to point
  ACTION: wait 2             — Wait N seconds
  ACTION: screenshot          — Take new screenshot to reassess
  ACTION: done TASK_COMPLETE  — Task is finished

IMPORTANT RULES:
1. Be precise with coordinates. Look at the screenshot carefully.
2. If you're unsure about a button's position, output ACTION: screenshot to get a fresh view.
3. Wait after clicks/actions for UI to respond (ACTION: wait 1).
4. Output multiple actions if you can chain them confidently.
5. After completing the task, output ACTION: done with description.
6. NEVER output coordinates like (0,0) unless you actually mean the top-left corner.
7. For text input fields: click the field first, wait briefly, then type.
8. Common key combos: Return, ctrl+w, alt+F4, ctrl+l, super (activities overview)"""


# ── Agent Core ────────────────────────────────

class VisionBrain:
    """The brain — coordinates eyes and hands in a loop."""

    def __init__(self, task="", max_steps=30, step_delay=2.0):
        self.eyes = VisionEyes(model="kimi-k2.6")
        self.task = task
        self.max_steps = max_steps
        self.step_delay = step_delay
        self.history = []  # (screenshot_path, llm_response, actions)
        self.step = 0

    def _build_prompt(self, step_num):
        """Build the user message for this step."""
        parts = [f"STEP {step_num}/{self.max_steps}"]
        if self.task:
            parts.append(f"TASK: {self.task}")
        if self.history:
            last = self.history[-1]
            if last[2]:  # actions
                parts.append(f"PREVIOUS ACTIONS: {'; '.join(last[2])}")
        parts.append("Look at this screenshot and output actions to progress the task. If the task is complete, output ACTION: done.")
        return "\n".join(parts)

    def run_step(self):
        """Single iteration: screenshot → LLM → parse → execute."""
        self.step += 1
        print(f"\n{'='*60}")
        print(f"  STEP {self.step}/{self.max_steps}")
        print(f"{'='*60}")

        # 1. Screenshot
        screen_path = f"/tmp/vision_step_{self.step}.png"
        img = take_screenshot(screen_path)
        if img is None:
            print("[Brain] FATAL: Cannot take screenshot. Is the GNOME Shell extension loaded?")
            print("[Brain] Try: logout/login, then check: gnome-extensions info screenshotService@hermes")
            return False

        # 2. Ask vision model
        prompt = self._build_prompt(self.step)
        print(f"[Brain] Asking kimi-k2.6...")
        response = self.eyes.describe(img, f"{SYSTEM_PROMPT}\n\n{prompt}")

        if not response:
            print("[Brain] No response from vision model.")
            time.sleep(self.step_delay)
            return True

        print(f"[Brain] LLM Response:\n{response[:500]}{'...' if len(response)>500 else ''}")

        # 3. Parse and execute actions
        actions = parse_and_execute(response)

        # 4. Check for done
        for act in (actions or []):
            if "done" in act.lower():
                print(f"\n[Brain] ✅ TASK COMPLETE: {act}")
                self.history.append((screen_path, response, actions))
                return False

        self.history.append((screen_path, response, actions))

        # 5. Wait for UI to update
        if actions:
            print(f"[Brain] Executed {len(actions)} actions. Waiting {self.step_delay}s...")
            time.sleep(self.step_delay)
        else:
            print("[Brain] No actions parsed. Waiting...")
            time.sleep(self.step_delay)

        return True  # continue

    def run(self):
        """Main agent loop."""
        print(f"\n🤖 Vision Agent v3 starting...")
        print(f"   Task: {self.task}")
        print(f"   Max steps: {self.max_steps}")
        print(f"   Vision: kimi-k2.6 (Ollama Cloud)")
        print(f"   Input: xdotool (Wayland-aware)")
        print(f"   Screenshot: GNOME Shell DBus extension")
        print()

        for i in range(self.max_steps):
            cont = self.run_step()
            if not cont:
                break

        print(f"\n{'='*60}")
        print(f"  SESSION COMPLETE — {self.step} steps executed")
        print(f"{'='*60}")
        return self.history


# ── Interactive Mode ──────────────────────────

def interactive():
    """Chat-style interactive mode — user gives tasks one at a time."""
    brain = VisionBrain(task="", max_steps=15)
    print("\n🤖 Vision Agent v3 — Interactive Mode")
    print("   Type a task, or 'quit' to exit.\n")

    while True:
        try:
            task = input("🎯 Task: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Brain] Exiting.")
            break

        if task.lower() in ("quit", "exit", "q"):
            break
        if not task:
            continue

        brain.task = task
        brain.step = 0
        brain.history = []
        brain.run()


# ── Entry Point ───────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Vision-driven desktop agent v3")
    parser.add_argument("task", nargs="?", default="", help="Task to execute")
    parser.add_argument("--steps", type=int, default=30, help="Max automation steps")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between steps (seconds)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive chat mode")
    args = parser.parse_args()

    if args.interactive or not args.task:
        interactive()
    else:
        brain = VisionBrain(task=args.task, max_steps=args.steps, step_delay=args.delay)
        brain.run()