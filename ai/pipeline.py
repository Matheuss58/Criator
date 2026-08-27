# -*- coding: utf-8 -*-
"""CLI estável do Criator. Toda a inteligência vive em criator_engine.py."""
import os
import sys

from criator_engine import create_edit
from logger import fail


def main():
    if len(sys.argv) < 7:
        raise RuntimeError("Uso: pipeline.py video audio resolucao duracao fps output [modo]")
    video, audio, resolution, duration, _fps, output = sys.argv[1:7]
    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
    create_edit(video, audio, resolution, float(duration), output)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        fail("PIPELINE", str(exc))
        raise
