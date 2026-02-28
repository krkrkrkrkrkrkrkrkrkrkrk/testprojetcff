@echo off
title SCAT Panel - Build Client
echo.
echo  Building SCAT Panel Client...
echo.

pip install pyinstaller websockets psutil >nul 2>&1

pyinstaller --onefile ^
    --name "SCAT Panel" ^
    --hidden-import websockets ^
    --hidden-import websockets.legacy ^
    --hidden-import websockets.legacy.client ^
    --uac-admin ^
    --clean ^
    client.py

echo.
if exist "dist\SCAT Panel.exe" (
    echo  [OK] Build complete!
    echo  EXE: dist\SCAT Panel.exe
    echo.
    echo  IMPORTANT: Before building, edit SERVER in client.py
    echo  to your actual server address.
) else (
    echo  [FAIL] Build failed. Check errors above.
)
echo.
pause
