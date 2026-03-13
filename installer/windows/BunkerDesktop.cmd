@echo off
rem  BunkerDesktop Launcher - thin wrapper that calls the PowerShell script
rem  This exists so desktop shortcuts can target a .cmd file.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0BunkerDesktop.ps1"