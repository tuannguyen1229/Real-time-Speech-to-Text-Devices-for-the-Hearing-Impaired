@echo off
chcp 65001 >nul
title Mat Kinh Ho Tro Giao Tiep - NCKH 2025
color 0A

echo ========================================
echo    MAT KINH HO TRO GIAO TIEP
echo    Nghien cuu khoa hoc sinh vien 2025
echo ========================================
echo.

cd /d "%~dp0"

REM Kich hoat Python virtual environment
echo [0/4] Kich hoat Python environment...
call .venv\Scripts\activate

echo [1/4] Khoi dong ESP32 Audio Server...
start "ESP32 Audio Server" cmd /k "title ESP32 Audio Server && cd /d %~dp0 && .venv\Scripts\activate && python final_lap\esp32_realtime_server.py"

echo [2/4] Doi server khoi dong...
timeout /t 3 /nobreak > nul

echo [3/4] Khoi dong Cloudflare Tunnel...
start "Cloudflare Tunnel" cmd /k "title Cloudflare Tunnel && cd /d %~dp0 && cloudflared tunnel --config final_lap\config.yml run esp32-server"

echo [4/4] Khoi dong Web Portal (with WiFi Manager)...
timeout /t 2 /nobreak > nul
start "Web Portal" cmd /k "title Web Portal && cd /d %~dp0 && .venv\Scripts\activate && cd web_portal && python app.py"

echo.
echo *** Tat ca dich vu da duoc khoi dong! ***
echo.
echo THONG TIN HE THONG:
echo ========================================
echo ESP32 Audio Server: http://localhost:8765
echo Public Tunnel: https://esp32.ptitavitech.online
echo Web Portal (with WiFi Manager): http://localhost:5000
echo.

REM Lay IP address cho mobile
echo URL cho dien thoai:
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    for /f "tokens=1" %%j in ("%%i") do (
        echo    http://%%j:5000
    )
)

echo.
echo HUONG DAN SU DUNG:
echo ========================================
echo 1. Truy cap Web Portal de quan ly thiet bi
echo 2. Them mat kinh moi vao he thong
echo 3. Upload code ESP32 va ket noi
echo 4. Bat dau su dung tinh nang nhan dien giong noi
echo.
echo *** Nhan phim bat ky de TAT TAT CA dich vu ***
pause > nul

echo.
echo Dang tat tat ca dich vu...
taskkill /f /im python.exe 2>nul
taskkill /f /im cloudflared.exe 2>nul
echo Da tat tat ca dich vu!
timeout /t 2 /nobreak > nul
