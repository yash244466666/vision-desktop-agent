#!/usr/bin/env python3
"""
VISION EYES v3.1 — Screen analyzer using Ollama Cloud vision API.
- Describes screen using cloud vision models (qwen3-vl, kimi-k2.6) via Ollama Cloud.
- Finds exact coordinates using OCR (EasyOCR) or OpenCV template matching.
- Never relies on LLM for raw (x,y) — LLM says *what* to click, OCR says *where*.
- Uses `requests` library instead of curl subprocess for reliability.
"""

import io, os, sys, json, re, math, time, base64, subprocess
from PIL import Image
import numpy as np
import requests

# ── Ollama Cloud Config ──────────────────────
OLLAMA_CLOUD_URL = "https://ollama.com/v1/chat/completions"
REQUEST_TIMEOUT = 90  # seconds

def _get_api_key():
    """Extract Ollama Cloud API key from hermes auth."""
    try:
        auth_path = os.path.expanduser("~/.hermes/auth.json")
        with open(auth_path) as f:
            data = json.load(f)
        return data["credential_pool"]["ollama-cloud"][0]["access_token"]
    except Exception as e:
        print(f"[Eyes] WARNING: Could not load API key: {e}")
        return os.environ.get("OLLAMA_CLOUD_KEY", "")


class VisionEyes:
    """Looks at screen. Cloud LLM understands. OCR locates."""

    def __init__(self, model="qwen3-vl:235b-instruct"):
        self.model = model
        self.api_key = _get_api_key()
        self._ocr = None
        self.available = bool(self.api_key)
        if self.available:
            print(f"[Eyes] Cloud vision ready. Model: {self.model}")
        else:
            print(f"[Eyes] WARNING: No API key — falling back to OCR only")

    def _encode_image(self, image: Image.Image, max_dim=1280) -> str:
        """Resize if huge, encode to base64 PNG."""
        if image.width > max_dim or image.height > max_dim:
            ratio = max_dim / max(image.width, image.height)
            image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.LANCZOS)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG", optimize=True)
        return base64.b64encode(buffered.getvalue()).decode()

    # ── Cloud Vision LLM ──────────────────────

    def describe(self, image: Image.Image, question: str) -> str:
        """Ask cloud vision model what it sees."""
        if not self.available:
            return self._ocr_fallback(image)
        b64 = self._encode_image(image)
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            "temperature": 0.1,
            "max_tokens": 4096
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            resp = requests.post(
                OLLAMA_CLOUD_URL,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content", "").strip()
            # Reasoning models (kimi-k2.6) may put answer in 'reasoning' when 'content' is empty
            if not content:
                reasoning = msg.get("reasoning", "").strip()
                if reasoning:
                    # Extract actionable parts from reasoning (look for coordinates, ACTION lines)
                    lines = reasoning.split("\n")
                    useful = [l.strip() for l in lines if any(kw in l for kw in 
                             ["ACTION", "click", "coordinate", "pixel", "button", "position", "Cancel", "Share", "toggle"])]
                    if useful:
                        content = "\n".join(useful)
                    else:
                        # Return last few lines of reasoning as fallback
                        content = "\n".join(lines[-5:]).strip()
            return content
        except requests.exceptions.Timeout:
            print(f"[Eyes] Cloud vision timeout ({REQUEST_TIMEOUT}s)")
            return self._ocr_fallback(image)
        except requests.exceptions.HTTPError as e:
            print(f"[Eyes] Cloud vision HTTP error: {e.response.status_code} {e.response.text[:200]}")
            return self._ocr_fallback(image)
        except Exception as e:
            print(f"[Eyes] Cloud vision failed: {e}")
            return self._ocr_fallback(image)

    # ── OCR: Text Location ───────────────────

    def find_text(self, image: Image.Image, query: str, confidence=0.3) -> dict:
        """
        Use EasyOCR to find text matching `query`.
        Returns {"found": bool, "x": int, "y": int, "match": str}
        """
        try:
            import easyocr
            if self._ocr is None:
                print("[Eyes] Loading EasyOCR...")
                self._ocr = easyocr.Reader(['en'], gpu=False)
            arr = np.array(image)
            results = self._ocr.readtext(arr)
            qlow = query.lower()
            best = None
            best_conf = 0.0
            for (bbox, text, conf) in results:
                if conf < confidence:
                    continue
                tlow = text.lower()
                score = self._text_score(qlow, tlow)
                if score > best_conf:
                    best_conf = score
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    best = {
                        "found": True,
                        "x": int(sum(xs)/4),
                        "y": int(sum(ys)/4),
                        "match": text,
                        "conf": conf
                    }
            if best and best_conf > 0.3:
                print(f"[Eyes] OCR found '{query}' -> '{best['match']}' at ({best['x']}, {best['y']}) conf={best['conf']:.2f}")
                return best
            print(f"[Eyes] OCR could not find '{query}'")
            return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
        except Exception as e:
            print(f"[Eyes] OCR error: {e}")
            return {"found": False, "x": 0, "y": 0, "match": str(e), "conf": 0}

    def _text_score(self, q: str, t: str) -> float:
        """Fuzzy text match score."""
        if q in t:
            return 1.0
        if t in q:
            return 0.8
        qw = set(q.split())
        tw = set(t.split())
        if not qw:
            return 0.0
        return len(qw & tw) / len(qw)

    # ── Template: Icon Match ──────────────────

    def template_find(self, screenshot: Image.Image, template_path: str, threshold=0.7) -> dict:
        """OpenCV template matching for icons/images."""
        try:
            import cv2
            if not os.path.exists(template_path):
                return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
            ss = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            tpl = cv2.imread(template_path)
            if tpl is None:
                return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
            res = cv2.matchTemplate(ss, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                h, w = tpl.shape[:2]
                cx = max_loc[0] + w // 2
                cy = max_loc[1] + h // 2
                print(f"[Eyes] Template match at ({cx}, {cy}) score={max_val:.2f}")
                return {"found": True, "x": cx, "y": cy, "match": os.path.basename(template_path), "conf": max_val}
            return {"found": False, "x": 0, "y": 0, "match": "", "conf": max_val}
        except Exception as e:
            print(f"[Eyes] Template error: {e}")
            return {"found": False, "x": 0, "y": 0, "match": str(e), "conf": 0}

    # ── Combined Locate ───────────────────────

    def locate(self, image: Image.Image, target: str, templates_dir="/home/yash/vision_agent/templates") -> dict:
        """
        Find `target` on screen.
        Tries template first if available, then OCR text search.
        """
        tpath = os.path.join(templates_dir, f"{target.lower().replace(' ', '_')}.png")
        if os.path.exists(tpath):
            r = self.template_find(image, tpath)
            if r["found"]:
                return r
        r = self.find_text(image, target)
        if r["found"]:
            return r
        return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}

    # ── OCR Fallback for describe ────────────

    def _ocr_fallback(self, image: Image.Image) -> str:
        try:
            if self._ocr is None:
                import easyocr
                self._ocr = easyocr.Reader(['en'], gpu=False)
            results = self._ocr.readtext(np.array(image))
            lines = [f"{t} (conf {c:.2f})" for (_, t, c) in results]
            return "OCR dump:\n" + "\n".join(lines[:30])
        except Exception as e:
            return f"[OCR fallback failed: {e}]"

if __name__ == '__main__':
    print("[Eyes] Standalone test mode.")
    eyes = VisionEyes()
    print(f"[Eyes] Available: {eyes.available}")