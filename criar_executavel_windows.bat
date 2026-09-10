@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python nao foi encontrado. Instale pelo site https://www.python.org/downloads/
  echo Durante a instalacao, marque a opcao "Add Python to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean Summit.spec

if errorlevel 1 (
  echo.
  echo Nao foi possivel criar o executavel.
  pause
  exit /b 1
)

echo.
echo Pronto! O aplicativo esta em: dist\Summit.exe
echo Esse arquivo pode ser copiado para outro computador Windows.
pause
