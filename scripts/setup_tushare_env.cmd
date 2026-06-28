@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0setup_tushare_env.ps1" -Token %*
