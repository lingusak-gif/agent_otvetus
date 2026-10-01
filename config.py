import os
from dotenv import load_dotenv

load_dotenv()  # Загружает переменные из файла .env

# Настройки подключения к ИИ
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')

# Настройки запуска программы
APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
APP_PORT = int(os.getenv('APP_PORT', 5000))