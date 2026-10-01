# launcher.py
import subprocess
import re
import sys
import os
import shutil
import http.server
import socketserver
import threading
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = shutil.which("cloudflared") or r"C:\cloudflared\cloudflared.exe"
CLIENT_FILE = os.path.join(BASE_DIR, "public", "client.html")
FLASK_APP = os.path.join(BASE_DIR, "app.py")

# ️ НАСТРОЙКИ ПОРТОВ
FLASK_PORT = 5000
PUBLIC_PORT = 8000

# 🔧 НАСТРОЙКИ ДЛЯ АВТО-ОБНОВЛЕНИЯ GITHUB PAGES
GITHUB_REPO_PATH = r"D:\github-repos\agent_otvetus"  # ← Ваш путь!
GITHUB_INDEX_FILE = "index.html"

def free_port(port):
    """Автоматически освобождает порт, если он занят (Windows)"""
    try:
        # 1. Ищем процесс на порту
        cmd = f'netstat -ano | findstr :{port}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'LISTENING' in line:
                    # PID обычно в конце строки
                    pid = line.split()[-1]
                    print(f"️ Порт {port} занят процессом PID {pid}. Освобождаем...")
                    
                    # 2. Убиваем процесс
                    kill_cmd = f'taskkill /F /PID {pid}'
                    subprocess.run(kill_cmd, shell=True, capture_output=True)
                    print(f"✅ Порт {port} успешно освобожден.")
        else:
            print(f" Порт {port} свободен, запуск без очистки.")
    except Exception as e:
        print(f"⚠️ Не удалось проверить порт: {e}")

def find_tunnel_url():
    print("🔍 Запуск туннеля...")
    proc = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", f"http://localhost:{FLASK_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    for line in proc.stdout:
        line_stripped = line.strip()
        # Ищем ссылку (работает даже если в строке есть лишний текст)
        match = re.search(r'https://[a-zA-Z0-9.-]+\.trycloudflare\.com', line_stripped)
        if match:
            found_url = match.group(0)
            print(f"✅ Ссылка извлечена: {found_url}")
            return found_url, proc
    print("❌ Ссылка не найдена в выводе cloudflared")
    return None, proc

def update_client_html(url):
    """Заменяет ссылку в client.html на актуальную + добавляет версию для кэша"""
    if not os.path.exists(CLIENT_FILE):
        print(f"❌ Не найден: {CLIENT_FILE}")
        return False
    
    # 🔁 Генерируем случайную версию для обхода кэша браузера
    version = f"?v={random.randint(1000, 9999)}"
    url_with_cache_bust = url + version
    
    with open(CLIENT_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 1. Заменяем старую ссылку (с любой версией или без) на новую с версией
    new_content = re.sub(r'https://[a-zA-Z0-9.-]+\.trycloudflare\.com(\?v=\d+)?', url_with_cache_bust, content)
    
    # 2. Заменяем placeholder в скрытом блоке (для нового client.html)
    new_content = new_content.replace('<!-- TUNNEL_URL -->', url_with_cache_bust)
    
    # 3. Резерв: если в div пусто или старая ссылка — перезапишем содержимое div
    new_content = re.sub(
        r'(<div id="tunnel-link"[^>]*>)[^<]*(</div>)',
        f'\\1{url_with_cache_bust}\\2',
        new_content,
        flags=re.IGNORECASE
    )
    
    with open(CLIENT_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"✅ Обновлён локальный: {CLIENT_FILE}")
    print(f"   🔗 Ссылка с версией: {url_with_cache_bust}")
    return True

def push_to_github(url):
    """Автоматически копирует файл в репозиторий и делает push"""
    if not os.path.exists(GITHUB_REPO_PATH):
        print(f"⚠️ Репозиторий не найден: {GITHUB_REPO_PATH}")
        return False

    dest_file = os.path.join(GITHUB_REPO_PATH, GITHUB_INDEX_FILE)
    try:
        shutil.copy2(CLIENT_FILE, dest_file)

        commands = [
            (["git", "add", "."], "📥 Добавление файлов..."),
            (["git", "commit", "-m", f"🔄 Auto-update tunnel URL: {url}"], "💾 Фиксация..."),
            (["git", "push"], "📤 Отправка на GitHub...")
        ]

        for cmd, msg in commands:
            result = subprocess.run(cmd, cwd=GITHUB_REPO_PATH, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   {msg} ✅")
            else:
                stderr = result.stderr.strip()
                if "nothing to commit" in stderr or "working tree clean" in stderr:
                    print(f"   {msg} ℹ️ (изменений нет)")
                    return True
                print(f"   {msg} ❌ {stderr}")
                return False

        print("✅ Успешно обновлено на GitHub Pages!")
        return True
    except Exception as e:
        print(f" Ошибка Git: {e}")
        return False

def run_http_server():
    os.chdir(os.path.join(BASE_DIR, "public"))
    class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            super().end_headers()
    with socketserver.TCPServer(("", PUBLIC_PORT), NoCacheHandler) as httpd:
        print(f"🌐 Клиентская страница: http://localhost:{PUBLIC_PORT}/client.html")
        httpd.serve_forever()

def main():
    # 🧹 ШАГ 0: АВТОМАТИЧЕСКАЯ ОЧИСТКА ПОРТА ПЕРЕД ЗАПУСКОМ
    free_port(FLASK_PORT)

    url, tunnel_proc = find_tunnel_url()
    if not url:
        print("❌ Не удалось получить ссылку туннеля")
        return

    print(f"\n✅ Туннель готов: {url}")
    update_client_html(url)
    push_to_github(url)

    print(f"🚀 Запуск HTTP-сервера на порту {PUBLIC_PORT}...")
    threading.Thread(target=run_http_server, daemon=True).start()

    print("🤖 Запуск агента...")
    flask_proc = subprocess.Popen([sys.executable, FLASK_APP])
    try:
        flask_proc.wait()
    except KeyboardInterrupt:
        print("\n⏹️ Остановка...")
        tunnel_proc.terminate()
        flask_proc.terminate()

if __name__ == "__main__":
    main()