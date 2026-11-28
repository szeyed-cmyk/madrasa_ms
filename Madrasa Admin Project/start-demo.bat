@echo off
rem Public demo starter for Windows.
rem Double-click this file in the "Madrasa Admin Project" folder, then open http://localhost:8000
rem You will see the landing page. Click Live Demo for the three demo accounts, or Take the tour.
rem This sets DEMO_MODE=true and SEED_DEMO_DATA=true (sample school, reset on every start).
rem For a real school install, use start.bat instead — that does not create demo accounts.
setlocal
cd /d "%~dp0"
set DEMO_MODE=true
set SEED_DEMO_DATA=true
call "%~dp0start.bat"
