@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem .venv 是 Python 3.12 + OCR 环境（paddlepaddle / paddleocr）。
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 goto fail
  ".venv\Scripts\python.exe" -m pip install -r requirements-ocr.txt
  if errorlevel 1 goto fail
)
echo.
echo 请在浏览器打开 http://127.0.0.1:5050
echo 保持此窗口打开，按 Ctrl+C 停止服务。
".venv\Scripts\python.exe" app.py
pause
exit /b
:fail
echo 安装失败，请确认 Python 3.11/3.12 和网络可用。
pause
