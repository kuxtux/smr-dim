@echo off
REM ============================================================
REM  PMSI SMR - lancement de l'application (Windows)
REM  Cree l'environnement virtuel au premier lancement,
REM  installe les dependances puis ouvre l'application.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERREUR : Python est introuvable.
        echo Installez Python depuis le Microsoft Store : application Python
        echo de la Python Software Foundation, version la plus recente,
        echo 3.10 au minimum. Si le Store est bloque sur ce poste, installez-le
        echo depuis https://www.python.org/downloads/ en cochant
        echo "Add python.exe to PATH". Relancez ensuite ce script.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
)

echo Verification des dependances...
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

echo Lancement de PMSI SMR...
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false
pause
