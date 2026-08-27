# -*- coding: utf-8 -*-
import json
import sys
import time

_START = time.time()

def _write(line):
    print(line, flush=True)

def log(stage, message):
    _write(f"[{stage}] {message}")

def progress(percent, step, message=None):
    percent = int(max(0, min(100, percent)))
    payload = {
        "progress": percent,
        "step": step,
        "message": message or step,
        "elapsed": round(time.time() - _START, 2),
    }
    _write("STATUS:" + json.dumps(payload, ensure_ascii=False))
    _write(f"PROGRESS:{percent}")

def fail(stage, message):
    payload = {
        "step": stage,
        "message": message,
        "elapsed": round(time.time() - _START, 2),
    }
    _write("ERROR:" + json.dumps(payload, ensure_ascii=False))
    print(message, file=sys.stderr, flush=True)