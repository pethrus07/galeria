@echo off
rem Abre a tela de limpeza da galeria em http://127.0.0.1:8765
cd /d "%~dp0"
start "" http://127.0.0.1:8765
"%USERPROFILE%\.venvs\galeria\Scripts\python.exe" src\tela.py
