@echo off
setlocal
if "%PYTHON_COMMAND%"=="" (
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON_COMMAND=.venv\Scripts\python.exe"
    ) else (
        set "PYTHON_COMMAND=python"
    )
)

REM Read the version straight out of src\gui.py so the exe name can never drift from
REM what the app reports in its UI. Parsed rather than imported: importing gui.py would
REM run the whole module.
set "APP_VERSION="
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"APP_VERSION" src\gui.py') do set RAW_VERSION=%%v
set RAW_VERSION=%RAW_VERSION: =%
set RAW_VERSION=%RAW_VERSION:"=%
set "APP_VERSION=%RAW_VERSION%"

if "%APP_VERSION%"=="" (
    echo Could not read APP_VERSION from src\gui.py.
    pause
    exit /b 1
)
echo Building Switch2ProConnect_%APP_VERSION%_(ShFr_UI_Mod).exe

REM Remove the spec files this script generated on earlier runs. PyInstaller writes one
REM named after --name, so bumping the version would otherwise leave a new orphan behind
REM every release. Only this script's own specs are touched: the "_log" ones belong to
REM package_with_log.bat, and gui.spec is left alone entirely.
if exist "Switch2Connect.spec" del /q "Switch2Connect.spec"
if exist "Switch2ProConnect.spec" del /q "Switch2ProConnect.spec"
for %%f in ("Switch2Connect_v*.spec" "Switch2ProConnect_v*.spec") do (
    echo %%~nf| findstr /i /e "_log" >nul || del /q "%%f"
)

set "CONFIG_FILE=config.yaml"
set "PACKAGE_CONFIG_DIR=package_temp"
set "PACKAGE_CONFIG_FILE=%PACKAGE_CONFIG_DIR%\config.yaml"

if not exist "%CONFIG_FILE%" (
    echo Missing %CONFIG_FILE%.
    pause
    exit /b 1
)

if exist "%PACKAGE_CONFIG_DIR%" rmdir /S /Q "%PACKAGE_CONFIG_DIR%"
mkdir "%PACKAGE_CONFIG_DIR%"
if errorlevel 1 (
    echo Failed to create %PACKAGE_CONFIG_DIR%.
    pause
)

copy /Y "%CONFIG_FILE%" "%PACKAGE_CONFIG_FILE%" >nul
if errorlevel 1 (
    echo Failed to create package config.
    rmdir /S /Q "%PACKAGE_CONFIG_DIR%" >nul 2>nul
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\prepare_package_config.ps1" -Path "%PACKAGE_CONFIG_FILE%"
if errorlevel 1 (
    echo Failed to reset package-only settings.
    rmdir /S /Q "%PACKAGE_CONFIG_DIR%" >nul 2>nul
    pause
    exit /b 1
)

REM Adopt the reset config as the repository copy, so the file in the project root always
REM matches what ships inside the exe. The reset copy was made from this same file and
REM only forces package defaults (including Power Saving Off and both warnings enabled), so this
REM changes nothing else. Done before the build, so the two stay in step even if the
REM build then fails.
copy /Y "%PACKAGE_CONFIG_FILE%" "%CONFIG_FILE%" >nul
if errorlevel 1 (
    echo Failed to update %CONFIG_FILE% with the reset settings.
    rmdir /S /Q "%PACKAGE_CONFIG_DIR%" >nul 2>nul
    pause
    exit /b 1
)

%PYTHON_COMMAND% -m PyInstaller -y --noconsole --onefile --clean --paths src --add-binary "drivers/WinUHid.dll;drivers" --add-binary "drivers/WinUHidDevs.dll;drivers" --add-data "resources;resources" --add-data "%PACKAGE_CONFIG_FILE%;resources" --add-data "drivers/install_driver.ps1;drivers" --add-data "drivers/install.bat;drivers" --add-data "drivers/uninstall_driver.ps1;drivers" --add-data "drivers/uninstall.bat;drivers" --add-data "drivers/WinUHidDriver.inf;drivers" --add-data "drivers/WinUHidDriver.dll;drivers" --add-data "drivers/winuhiddriver.cat;drivers" --add-data "drivers/WinUHidDriver.cer;drivers" --add-data "drivers/hidhide;drivers/hidhide" --add-data "src;src" --collect-all vgamepad --collect-all imufusion --collect-all bleak --collect-all winrt --collect-all hid --collect-all libusb_package --hidden-import gui_listeners --hidden-import gui_wizards --hidden-import gui_player_block --hidden-import gui_widgets --hidden-import gui_drivers_mixin --hidden-import gui_settings_mixin --hidden-import imufusion --hidden-import hid --hidden-import usb.core --hidden-import usb.util --hidden-import libusb_package --hidden-import driver_install_helper --hidden-import usb_hid_controller --hidden-import hidhide --hidden-import usbip_server --name "Switch2ProConnect_%APP_VERSION%_(ShFr_UI_Mod)" --icon="resources/images/icon.ico" src/gui.py
set "BUILD_EXIT=%ERRORLEVEL%"

rmdir /S /Q "%PACKAGE_CONFIG_DIR%" >nul 2>nul
if not "%BUILD_NO_PAUSE%"=="1" pause
exit /b %BUILD_EXIT%
