@echo off
chcp 65001 >nul
title قياس الشهر — ذرّات التحليل (قياس فقط)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_month.ps1"
