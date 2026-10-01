from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
import config
import os
import base64
import secrets
from io import BytesIO
from datetime import datetime
import requests
from dotenv import load_dotenv

# 🔔 Загружаем переменные из .env (токен бота, Chat ID)
load_dotenv()

def send_telegram_notify(message):
    """Отправляет уведомление в Telegram"""
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    
    if not token or not chat_id:
        print("⚠️ Telegram не настроен — пропускаем уведомление")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram-уведомление отправлено")
            return True
        else:
            print(f"❌ Telegram ошибка: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка отправки Telegram: {e}")
        return False

# === Инициализация Flask ===
app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "users.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# === Инициализация расширений ===
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per day", "20 per hour"]
)
limiter.init_app(app)

# === OpenAI клиент ===
client = OpenAI(api_key=config.OPENAI_API_KEY)

# === Модели БД ===
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    chats = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    file_reference = db.Column(db.String(200), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# === Создание БД и тестового пользователя ===
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')
        admin.set_password('AdminPass123!')
        db.session.add(admin)
        db.session.commit()
        print("✅ Создан тестовый пользователь: admin / AdminPass123!")

# === Системный промпт ===
def load_system_prompt():
    try:
        with open('system_prompt.txt', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Ты — профессиональный юрист для граждан РФ."
SYSTEM_PROMPT = load_system_prompt()

# === Извлечение текста ===
def extract_text_from_pdf(file_bytes):
    # 1. Пробуем pdfplumber (лучший для текстовых PDF)
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            if full_text.strip(): return full_text.strip()
    except Exception as e:
        print(f"⚠️ pdfplumber ошибка: {e}")

    # 2. Пробуем PyPDF2 (резервный)
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        full_text = "\n".join([page.extract_text() or "" for page in reader.pages])
        if full_text.strip(): return full_text.strip()
    except Exception as e:
        print(f"⚠️ PyPDF2 ошибка: {e}")

    # 3. Пробуем PyMuPDF/fitz (идеален для сканов и сложных файлов)
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if len(doc) > 0:
            # Сначала проверяем, есть ли вообще вычитываемый текст
            text_check = "".join([page.get_text() or "" for page in doc])
            if len(text_check.strip()) > 50:
                doc.close()
                return text_check.strip()
            
            # Если текста мало → это скан/картинка. Рендерим 1-ю страницу в PNG для Vision API
            page = doc[0]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            doc.close()
            return {"type": "image", "data": base64.b64encode(img_bytes).decode('utf-8'), "note": "[PDF-скан: OCR через Vision]"}
    except Exception as e:
        print(f"⚠️ PyMuPDF ошибка: {e}")

    print("❌ Все методы извлечения PDF провалились. Проверьте файл или библиотеки.")
    return None

def extract_text_from_docx(file_bytes):
    try:
        import docx
        doc = docx.Document(BytesIO(file_bytes))
        return "\n".join([para.text for para in doc.paragraphs]).strip()
    except: return None

def extract_text_from_txt(file_bytes):
    try: return file_bytes.decode('utf-8', errors='ignore').strip()
    except: return None

def extract_text(file_bytes, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf': return extract_text_from_pdf(file_bytes)
    if ext in ['.docx', '.doc']: return extract_text_from_docx(file_bytes)
    if ext == '.txt': return extract_text_from_txt(file_bytes)
    return None

# === Маршруты авторизации ===
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            return redirect(url_for('index'))
        return render_template('login.html', error='Неверный логин или пароль')
    return render_template('login.html', error=None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    ALLOW_SELF_REGISTRATION = True  # 🔐 Поставьте False, чтобы закрыть регистрацию
    if not ALLOW_SELF_REGISTRATION: return 'Регистрация только через администратора', 403
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not username or not password: return render_template('register.html', error='Заполните все поля')
        if password != confirm: return render_template('register.html', error='Пароли не совпадают')
        if len(password) < 8: return render_template('register.html', error='Пароль мин. 8 символов')
        if User.query.filter_by(username=username).first(): return render_template('register.html', error='Пользователь уже существует')
        
        # Создаём пользователя
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # 🔔 ОТПРАВЛЯЕМ УВЕДОМЛЕНИЕ В TELEGRAM
        send_telegram_notify(
            f"🆕 <b>Новый клиент</b>\n\n"
            f"👤 Логин: <code>{username}</code>\n"
            f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"🔗 <a href='https://lingusak-gif.github.io/agent_otvetus/'>Открыть агент</a>"
        )
        
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html', error=None)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# === Основной чат ===
@app.route('/')
@login_required
def index():
    return render_template('index.html', username=current_user.username)

@app.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def chat():
    data = request.json
    user_msg = data.get('message', '')
    file_b64 = data.get('file')
    file_name = data.get('fileName', '')
    file_type = data.get('fileType', '')
    
    user_chats = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp).all()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in user_chats[-10:]:
        messages.append({"role": msg.role, "content": msg.content})
    
    final_prompt = user_msg
    
    if file_b64 and file_name:
        file_bytes = base64.b64decode(file_b64)
        extracted = extract_text(file_bytes, file_name)
        if isinstance(extracted, dict) and extracted.get("type") == "image":
            img_b64 = extracted['data']
            content = [{"type": "text", "text": user_msg + " " + extracted.get("note", "")}]
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}})
            messages.append({"role": "user", "content": content})
        elif extracted:
            if len(extracted) > 30000: extracted = extracted[:30000] + "\n\n[...текст обрезан...]"
            final_prompt += f"\n\n📄 КОНТЕНТ ФАЙЛА «{file_name}»:\n{extracted}\n\n"
            messages.append({"role": "user", "content": final_prompt})
        else:
            final_prompt += f"\n\n[⚠️ Не удалось прочитать файл {file_name}]"
            messages.append({"role": "user", "content": final_prompt})
    else:
        messages.append({"role": "user", "content": final_prompt})
    
    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=2500
        )
        reply = response.choices[0].message.content
        file_note = f" [файл: {file_name}]" if file_name else ""
        db.session.add(ChatMessage(user_id=current_user.id, role='user', content=(user_msg or "[Файл]") + file_note))
        db.session.add(ChatMessage(user_id=current_user.id, role='assistant', content=reply))
        db.session.commit()
        return jsonify({'success': True, 'message': reply})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# === Экспорт истории ===
@app.route('/api/export')
@login_required
def export_chat():
    messages = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp).all()
    content = f"История чата: {current_user.username}\n{'='*50}\n\n"
    for msg in messages:
        ts = msg.timestamp.strftime('%Y-%m-%d %H:%M')
        emoji = '👤' if msg.role == 'user' else '🤖'
        content += f"[{ts}] {emoji}\n{msg.content}\n\n"
    buffer = BytesIO()
    buffer.write(content.encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, mimetype='text/plain', as_attachment=True, download_name=f'chat_{current_user.username}.txt')

@app.route('/status')
def status():
    return jsonify({'status': 'online', 'model': config.OPENAI_MODEL})

if __name__ == '__main__':
    print("🚀 Агент с авторизацией запущен! http://127.0.0.1:5000")
    print("🔐 Тестовый вход: admin / AdminPass123! (смените пароль!)")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)