@echo off
rem Start the bridge (Windows). Toggle forwarding with Ctrl+Alt+Shift+K.
"%~dp0host\.venv\Scripts\python.exe" "%~dp0host\bridge.py" %*
