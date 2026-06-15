@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   荷花池互動展項 - 本地伺服器
echo   開啟 http://localhost:8080/index.html
echo   關閉此視窗即停止伺服器
echo ============================================================
echo.
echo （載入 Blender 精靈圖時「必須」用本機伺服器開啟，
echo   因為水面折射會讀取畫面像素，直接雙擊 index.html 會被瀏覽器擋下。）
echo.
start "" http://localhost:8080/index.html
python -m http.server 8080
