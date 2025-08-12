@echo off
setlocal

echo #################################################
echo #  Compiling DocumentAI Helper for Windows      #
echo #################################################

REM --- Configuration ---
set "PROJECT_ROOT=C:\Users\admin7\OneDrive - Americana Building Products\Projects\PythonHelpDeskAPP"
set "SCRIPT_NAME=%PROJECT_ROOT%\documentai.py"
set "EXE_NAME=DocumentAI"
set "ICON_PATH=%PROJECT_ROOT%\resources\documentai.ico"

echo.
echo --- Cleaning up previous build artifacts ---
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist %EXE_NAME%.spec del %EXE_NAME%.spec
echo Cleanup complete.
echo.

echo --- Running PyInstaller to create the executable ---
pyinstaller ^
  --clean ^
  --noconfirm ^
  --name "%EXE_NAME%" ^
  --onefile ^
  --windowed ^
  --icon "%ICON_PATH%" ^
  --add-data "%PROJECT_ROOT%\resources;resources" ^
  --add-data "%PROJECT_ROOT%\ai_chatbot_app;ai_chatbot_app" ^
  --hidden-import PySide6 ^
  --hidden-import pydantic ^
  --hidden-import pydantic_core ^
  --hidden-import typing_extensions ^
  --hidden-import langchain_core ^
  --hidden-import langchain_huggingface ^
  "%SCRIPT_NAME%"

echo.
echo --- Build process finished! ---
echo Your executable can be found in the 'dist' folder.
echo.
pause
