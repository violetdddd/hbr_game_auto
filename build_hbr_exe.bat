@echo off
setlocal EnableExtensions
REM Run from the directory containing this BAT file.
cd /d "%~dp0"

for %%D in (char-data char-images templates) do (
    if not exist "assets\%%D\" (echo ERROR: missing assets\%%D & exit /b 1)
)
if not exist "hbrf\axisWebsite\mapping.json" (echo ERROR: missing mapping.json & exit /b 1)
if not exist "hbrf\axisWebsite\sav_to_hbrf.py" (echo ERROR: missing sav_to_hbrf.py & exit /b 1)
if not exist "hbrf\model.py" (echo ERROR: missing hbrf\model.py & exit /b 1)
if not exist "scripts\blank.hbrf" (echo ERROR: missing scripts\blank.hbrf & exit /b 1)
if not exist "scripts\HS-65.hbrf" (echo ERROR: missing scripts\HS-65.hbrf & exit /b 1)
if not exist "hbr_gui.py" (echo ERROR: missing hbr_gui.py & exit /b 1)
if not exist "run_battle.py" (echo ERROR: missing run_battle.py & exit /b 1)
if not exist "run_card_game.py" (echo ERROR: missing run_card_game.py & exit /b 1)

set "STAGE=%TEMP%\HBRTool_assets_%RANDOM%_%RANDOM%"
mkdir "%STAGE%\assets" || exit /b 1
for %%D in (char-data char-images templates) do (
    robocopy "assets\%%D" "%STAGE%\assets\%%D" /E /XD __pycache__ .git .vscode /XF *.pyc *.pyo .gitignore >nul
    if errorlevel 8 goto :fail
)

python -m PyInstaller --noconfirm --clean --onedir --windowed --name HBRTool ^
  --add-data "%STAGE%\assets\char-data;assets\char-data" ^
  --add-data "%STAGE%\assets\char-images;assets\char-images" ^
  --add-data "%STAGE%\assets\templates;assets\templates" ^
  --add-data "hbrf\axisWebsite\mapping.json;hbrf\axisWebsite" ^
  --hidden-import=hbrf.axletool.axle_jpg_to_hbrf ^
  --hidden-import=piexif ^
  --hidden-import=lzstring ^
  --hidden-import run_battle --hidden-import run_card_game ^
  --hidden-import hbrf.axisWebsite.sav_to_hbrf ^
  --hidden-import hbrf.model --collect-submodules config ^
  --icon "logo.ico" ^
  --add-data "logo.ico;." ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngineQuick ^
  --exclude-module PySide6.QtPdf ^
  --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module tkinter ^
  --exclude-module PIL.AvifImagePlugin ^
  --exclude-module PySide6.Qt3DCore ^
  --exclude-module PySide6.Qt3DRender ^
  --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtDataVisualization ^
  --exclude-module PySide6.QtSensors ^
  --exclude-module PySide6.QtWebSockets ^
  --exclude-module PySide6.QtNetwork ^
  --exclude-module PySide6.QtWebChannel ^
  --exclude-module PySide6.QtSql ^
  hbr_gui.py
if errorlevel 1 goto :fail

if exist "dist\HBRTool\scripts" rmdir /s /q "dist\HBRTool\scripts"
mkdir "dist\HBRTool\scripts" || goto :fail
copy /y "scripts\blank.hbrf" "dist\HBRTool\scripts\blank.hbrf" >nul || goto :fail
copy /y "scripts\HS-65.hbrf" "dist\HBRTool\scripts\HS-65.hbrf" >nul || goto :fail
rmdir /s /q "%STAGE%"
echo Build complete: dist\HBRTool\HBRTool.exe

REM ==============================================
REM PyInstaller 打包成功之后
REM ==============================================

REM 删除不需要的 OpenCV FFmpeg DLL
if exist "dist\HBRTool\_internal\cv2\opencv_videoio_ffmpeg500_64.dll" (
    del /f /q "dist\HBRTool\_internal\cv2\opencv_videoio_ffmpeg500_64.dll"
    echo Removed OpenCV FFmpeg DLL.
)
echo.
echo Packaging completed!
pause
exit /b 0


REM ==============================================
REM 打包失败时执行
REM ==============================================
:fail
set "EXITCODE=%ERRORLEVEL%"
if exist "%STAGE%" rmdir /s /q "%STAGE%"
if "%EXITCODE%"=="0" set "EXITCODE=1"
echo ERROR: packaging failed.
exit /b %EXITCODE%
