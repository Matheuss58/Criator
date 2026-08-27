# -*- coding: utf-8 -*-
import os
import subprocess
import sys
from typing import Dict

from config import DEMUCS_MODEL, DEMUCS_REQUIRED
from logger import log


def separate_stems(audio_path: str, output_dir: str = None, required: bool = None) -> Dict:
    required = DEMUCS_REQUIRED if required is None else required
    output_dir = output_dir or os.path.join(os.path.dirname(audio_path) or ".", "stems")
    os.makedirs(output_dir, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=vocals",
        "--name",
        DEMUCS_MODEL,
        "-o",
        output_dir,
        audio_path,
    ]
    log("DEMUCS", f"Separando stems com {DEMUCS_MODEL}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    except Exception as exc:
        message = f"Demucs falhou ao iniciar: {exc}"
        log("DEMUCS", message)
        if not required:
            log("DEMUCS", "Fallback ativo: usando audio completo")
        return {"ok": False, "error": message, "vocals": None, "no_vocals": None, "output_dir": output_dir}

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Demucs falhou").strip()
        log("DEMUCS", message[-1200:])
        if not required:
            log("DEMUCS", "Fallback ativo: usando audio completo")
        return {"ok": False, "error": message[-4000:], "vocals": None, "no_vocals": None, "output_dir": output_dir}

    vocals = None
    no_vocals = None
    for root, _, files in os.walk(output_dir):
        for filename in files:
            full_path = os.path.join(root, filename)
            if filename == "vocals.wav":
                vocals = full_path
            elif filename == "no_vocals.wav":
                no_vocals = full_path

    ok = bool(vocals or no_vocals)
    log("DEMUCS", f"Stems prontos | vocals={bool(vocals)} instrumental={bool(no_vocals)}")
    return {
        "ok": ok,
        "error": None if ok else "Demucs concluiu, mas nenhum stem foi encontrado.",
        "vocals": vocals,
        "no_vocals": no_vocals,
        "output_dir": output_dir,
    }


def extract_vocals(audio_path: str, output_dir: str = None) -> str:
    result = separate_stems(audio_path, output_dir=output_dir)
    return result.get("vocals")
