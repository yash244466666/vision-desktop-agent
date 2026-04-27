#!/usr/bin/env python3
"""
VISION EYES v3 — Screen analyzer using Ollama Cloud vision API.
- Describes screen using kimi-k2.6 (cloud vision model via Ollama Cloud).
- Finds exact coordinates using OCR (EasyOCR) or OpenCV template matching.
- Never relies on LLM for raw (x,y) — LLM says *what* to click, OCR says *where*.
"""

import io, os, sys, json, re, math, time, base64, subprocess
from PIL import Image
import numpy as np

# ── Ollama Cloud Config ──────────────────────
OLLAMA_CLOUD_URL = "https://ollama.com/v1/chat/completions"


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

    def __init__(self, model="kimi-k2.6"):
        self.model = model
        self.api_key = _get_api_key()
        self._ocr = None
        self.available = bool(self.api_key)
        if self.available:
            print(f"[Eyes] Cloud vision ready. Model: {self.model}")
        else:
            print(f"[Eyes] WARNING: No API key — falling back to OCR only")

    def _encode_image(self, image, max_dim=1280):
        """Resize if huge, encode to base64 PNG."""
        if image.width > max_dim or image.height > max_dim:
            ratio = max_dim / max(image.width, image.height)
            image = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.LANCZOS)
        buffered = io.BytesIO()
        image.save(buffered, format="PNG", optimize=True)
        return base64.b64encode(buffered.getvalue()).decode()

    def describe(self, image, question):
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
            "max_tokens": 1024
        }
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "60", OLLAMA_CLOUD_URL],
                input=json.dumps(payload).encode(),
                capture_output=True,
                timeout=90
            )
            resp = json.loads(proc.stdout)
            return resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"[Eyes] Cloud vision failed: {e}")
            return self._ocr_fallback(image)

    def find_text(self, image, query, confidence=0.3):
        try:
            import easyocr
            if self._ocr is None:
                self._ocr = easyocr.Reader(['en'], gpu=False)
            arr = np.array(image)
            results = self._ocr.readtext(arr)
            qlow = query.lower()
            best = None
            best_conf = 0.0
            for (bbox, text, conf) in results:
                if conf < confidence:
                    continue
                score = self._text_score(qlow, text.lower())
                if score > best_conf:
                    best_conf = score
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    best = {"found": True, "x": int(sum(xs)/4), "y": int(sum(ys)/4), "match": text, "conf": conf}
            if best and best_conf > 0.3:
                return best
            return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
        except Exception as e:
            return {"found": False, "x": 0, "y": 0, "match": str(e), "conf": 0}

    def _text_score(self, q, t):
        if q in t: return 1.0
        if t in q: return 0.8
        qw = set(q.split())
        tw = set(t.split())
        return len(qw & tw) / len(qw) if qw else 0.0

    def template_find(self, screenshot, template_path, threshold=0.7):
        try:
            import cv2
            if not os.path.exists(template_path):
                return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
            ss = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            tpl = cv2.imread(template_path)
            if tpl is None:
                return {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}
            res = cv2.matchTemplate(ss, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                h, w = tpl.shape[:2]
                return {"found": True, "x": max_loc[0] + w // 2, "y": max_loc[1] + h // 2, "match": os.path.basename(template_path), "conf": max_val}
            return {"found": False, "x": 0, "y": 0, "match": "", "conf": max_val}
        except Exception as e:
            return {"found": False, "x": 0, "y": 0, "match": str(e), "conf": 0}

    def locate(self, image, target, templates_dir="templates"):
        tpath = os.path.join(templates_dir, f"{target.lower().replace(' ', '_')}.png")
        if os.path.exists(tpath):
            r = self.template_find(image, tpath)
            if r["found"]: return r
        r = self.find_text(image, target)
        return r if r["found"] else {"found": False, "x": 0, "y": 0, "match": "", "conf": 0}

    def _ocr_fallback(self, image):
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
    print("[Eyes] Standalone test.")
    eyes = VisionEyes()
    print(f"[Eyes] Available: {eyes.available}")