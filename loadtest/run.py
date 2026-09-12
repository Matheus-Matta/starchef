#!/usr/bin/env python
"""Ponto de entrada do teste de carga.

    python loadtest/run.py backend --duration 60
    python loadtest/run.py all --profile pesado

Roda so na mao. Nao entra em CI, nao entra no pytest: ele existe para
derrubar um ambiente descartavel de proposito.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from starchef_load.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
