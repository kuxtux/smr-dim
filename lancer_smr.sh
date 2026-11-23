#!/usr/bin/env bash
# ============================================================
#  PMSI SMR — lancement de l'application (Linux / macOS)
# ============================================================
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Création de l'environnement virtuel…"
    python3 -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip
fi

.venv/bin/python -m pip install --quiet -r requirements.txt

.venv/bin/python -m streamlit run app.py
