"""Quick test: facade-only render detection vs 3-image pipeline results."""

import json
import os
import time
from pathlib import Path

import anthropic

env_path = Path(__file__).resolve().parent.parent / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

RENDER_PROMPT = """Look at this building/property facade image. Is this a 3D render/CGI or a real photograph?
Return ONLY a JSON object: {"is_render": true/false, "render_confidence": 0.0-1.0}
Do NOT return an array."""

# (pid, 3-image is_render, 3-image confidence, facade_url)
facades = [
    ("34611687", False, 0.850, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/1c/30/c8/310463105.webp"),
    ("34012108", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/ea/3b/b8/279111154.webp"),
    ("34889224", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/b1/32/20/311480459.webp"),
    ("33550263", False, 0.850, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/0c/0e/60/251006716.webp"),
    ("34859570", False, 0.900, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/89/d2/aa/310233916.webp"),
    ("34599095", False, 0.850, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/34/1b/8c/300369588.webp"),
    ("34838187", False, 0.900, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/39/bd/0a/309290916.webp"),
    ("34708874", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/f5/a4/23/304401087.webp"),
    ("34567216", False, 0.900, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/0c/3e/78/298944569.webp"),
    ("34870356", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/74/53/a9/304993412.webp"),
    ("34212321", False, 0.850, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/61/a4/4a/285023516.webp"),
    ("34878274", False, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/84/4a/03/311009978.webp"),
    ("34888139", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/9e/04/be/311423651.webp"),
    ("34778025", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/62/39/96/307070213.webp"),
    ("34147921", True, 0.950, "https://img4.idealista.pt/blur/WEB_DETAIL-XL-L/0/id.pro.pt.image.master/67/0d/cb/282426034.webp"),
]

print(f"{'PID':<12} {'3img_render':>12} {'3img_conf':>10} {'facade_render':>14} {'facade_conf':>12} {'agree':>6}  facade_url")
print("-" * 130)

agree = 0
for pid, orig_render, orig_conf, url in facades:
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "url", "url": url}},
                {"type": "text", "text": RENDER_PROMPT},
            ]}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        r = json.loads(raw)
        facade_render = r.get("is_render")
        facade_conf = r.get("render_confidence")
        match = "Y" if facade_render == orig_render else "N"
        if facade_render == orig_render:
            agree += 1
        print(f"{pid:<12} {str(orig_render):>12} {orig_conf:>10.3f} {str(facade_render):>14} {facade_conf:>12.3f} {match:>6}  {url}")
    except Exception as e:
        print(f"{pid:<12} {str(orig_render):>12} {orig_conf:>10.3f} {'ERROR':>14} {'---':>12} {'':>6}  {e}")
    time.sleep(1.5)

print(f"\nAgreement (facade-only vs 3-image): {agree}/{len(facades)} ({100*agree/len(facades):.0f}%)")
