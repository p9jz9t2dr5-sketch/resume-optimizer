@echo off
REM ============================================================
REM  简历优化项目 - 一键启动（双击运行）
REM  会新开两个命令行窗口：后端(:8000) 与 前端(:3000)
REM  关闭这两个窗口即可停止服务
REM ============================================================
start "Resume-Backend" cmd /k "cd /d C:\Users\liangtian\Desktop\resume-optimizer\backend && set APP_ENV=local && set HTTP_PROXY= && set HTTPS_PROXY= && set ALL_PROXY= && set NO_PROXY=* && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
start "Resume-Frontend" cmd /k "cd /d C:\Users\liangtian\Desktop\resume-optimizer\frontend && npm run dev"
echo.
echo  [OK] 已启动两个服务窗口，请等待约 15 秒后访问：
echo   前端 : http://localhost:3000
echo   后端 : http://localhost:8000
echo.
echo  关闭那两个命令行窗口即可停止服务。
echo.
pause
