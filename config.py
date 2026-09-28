import os
from dotenv import load_dotenv

load_dotenv()

# Настройки GigaChat (долгосрочный ключ)
GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY', '')
GIGACHAT_MODEL = os.getenv('GIGACHAT_MODEL', 'GigaChat:latest')

APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
APP_PORT = int(os.getenv('APP_PORT', 5000))