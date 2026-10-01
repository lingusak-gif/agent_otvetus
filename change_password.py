# change_password.py
from app import app, db, User

with app.app_context():
    username = input("Логин пользователя: ").strip()
    password = input("Новый пароль: ").strip()
    
    user = User.query.filter_by(username=username).first()
    if user:
        user.set_password(password)
        db.session.commit()
        print(f"✅ Пароль для '{username}' изменён!")
    else:
        print(f"❌ Пользователь '{username}' не найден")

if __name__ == '__main__':
    app.run()  # Нужно для контекста Flask