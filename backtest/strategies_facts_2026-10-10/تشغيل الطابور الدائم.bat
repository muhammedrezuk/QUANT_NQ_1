@echo off
chcp 65001 >nul
title الطابور الدائم — قياس معمق (لا تغلق النافذة)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_queue.ps1"
