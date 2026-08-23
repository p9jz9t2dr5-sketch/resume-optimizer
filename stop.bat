@echo off
REM ============================================================
REM  简历优化项目 - 一键停止（双击运行）
REM  杀掉占用 8000 / 3000 端口的进程
REM ============================================================
echo 正在停止占用 8000 / 3000 端口的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
echo 完成。如有残留，请手动关闭对应的命令行窗口。
echo.
pause
