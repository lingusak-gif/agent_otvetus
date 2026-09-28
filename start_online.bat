   @echo off
   chcp 65001 >nul
   title 🤖 Legal AI Agent - Server

   echo 🚀 Запуск агента...
   start "Agent" python app.py

   timeout /t 5 /nobreak >nul

   echo 🌐 Запуск Cloudflare туннеля...
   start "Tunnel" cloudflared tunnel --url http://localhost:5000

   echo.
   echo ✅ Готово! Агент доступен по ссылке из второго окна.
   echo ⚠️  Не закрывайте окна, пока агент нужен.
   pause