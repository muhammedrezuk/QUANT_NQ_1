@echo off
chcp 65001 >nul
title قياس السنة — المشي إلى الأمام (قياس فقط)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_year.ps1"
