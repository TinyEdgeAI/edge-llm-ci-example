#!/usr/bin/env python3
"""Standalone sustained / thermal probe for a Jetson (or any Linux device with a
llama.cpp build). Loops generations for N minutes, recording decode tok/s + the
hottest thermal zone over time → a JSON time-series the TinyEdge platform's
analyzeSustained consumes. No dependencies beyond Python 3 + the llama binary.

  python3 sustained_probe.py /path/to/model.gguf [minutes] [out.json]

Temperature is read from /sys/class/thermal (no root). Override the binary with
TINYEDGE_LLAMA_CLI=/path/to/llama-completion if it's not at the default location.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MODEL = sys.argv[1] if len(sys.argv) > 1 else None
MINUTES = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
OUT = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/sustained.json")
if not MODEL:
    sys.exit("usage: python3 sustained_probe.py MODEL.gguf [minutes] [out.json]")

CLI = os.environ.get("TINYEDGE_LLAMA_CLI") or os.path.expanduser(
    "~/tinyedge/llama.cpp/build/bin/llama-completion"
)
PROMPT = (
    "The history of computing spans mechanical calculators, vacuum tubes, "
    "transistors and integrated circuits. Briefly explain what enabled this "
    "progression and what physical limits future hardware may face."
)

env = os.environ.copy()
env["LD_LIBRARY_PATH"] = f"/usr/local/cuda/lib64:{Path(CLI).parent}:" + env.get("LD_LIBRARY_PATH", "")
env["LC_ALL"] = "C"  # keep llama.cpp's perf numbers dot-decimal for the parser

CMD = [CLI, "-m", MODEL, "-p", PROMPT, "-n", "128", "-c", "1024",
       "-t", str(os.cpu_count() or 4), "--temp", "0", "--seed", "42",
       "-st", "--simple-io", "--ignore-eos", "-ngl", "99"]


def temp_c():
    best = None
    for z in Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            raw = int((z / "temp").read_text().strip())
        except Exception:
            continue
        c = raw / 1000.0 if abs(raw) > 1000 else float(raw)
        if -20 < c < 130 and (best is None or c > best):
            best = c
    return round(best, 1) if best is not None else None


def decode_tps(stderr):
    for ln in stderr.splitlines():
        if "eval time" in ln and "prompt eval time" not in ln:
            m = re.search(r"([\d.]+) tokens per second", ln)
            if m:
                return round(float(m.group(1)), 2)
    return None


samples = []
t0 = time.time()
deadline = t0 + MINUTES * 60
print(f"sustained probe · {Path(MODEL).name} · {MINUTES} min  (Ctrl-C to stop early)", flush=True)
try:
    while time.time() < deadline:
        r = subprocess.run(CMD, cwd=str(Path(MODEL).parent), env=env,
                           capture_output=True, text=True, timeout=600)
        tps = decode_tps(r.stderr)
        if tps is None:
            tail = "\n".join(r.stderr.splitlines()[-5:])
            sys.exit(f"could not parse tok/s (model path / binary OK?):\n{tail}")
        t = round(time.time() - t0, 1)
        tc = temp_c()
        samples.append({"t": t, "tokensPerSec": tps, "deviceTempC": tc})
        print(f"  t={t:>6.0f}s   {tps:>6.1f} tok/s   {tc}°C", flush=True)
except KeyboardInterrupt:
    print("\nstopped early", flush=True)

res = {"durationSec": round(time.time() - t0), "model": Path(MODEL).name, "samples": samples}
Path(OUT).write_text(json.dumps(res, indent=2))
if samples:
    temps = [s["deviceTempC"] for s in samples if s["deviceTempC"] is not None]
    print(f"\n{len(samples)} samples · cold {samples[0]['tokensPerSec']} → end "
          f"{samples[-1]['tokensPerSec']} tok/s · max {max(temps) if temps else '?'}°C  →  {OUT}",
          flush=True)
