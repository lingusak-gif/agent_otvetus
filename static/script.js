const chatArea = document.getElementById('chat-area');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const fileInput = document.getElementById('file-input');
const fileNameEl = document.getElementById('file-name');

let selectedFile = null;
let isSending = false;

// 1. Выбор файла
fileInput.addEventListener('change', (e) => {
    if (e.target.files[0]) {
        selectedFile = e.target.files[0];
        fileNameEl.textContent = `📄 ${selectedFile.name}`;
        fileNameEl.style.display = 'inline';
        console.log('✅ Файл выбран:', selectedFile.name, '| Размер:', selectedFile.size, 'байт');
    }
});

// 2. Добавление сообщения в чат
function addMessage(text, sender, fileLabel = '') {
    const div = document.createElement('div');
    div.classList.add('message', sender);
    const avatar = sender === 'user' ? '👤' : '🤖';
    const badge = fileLabel ? `<span style="background:#e9ecef;padding:2px 8px;border-radius:4px;font-size:0.8em;margin-left:8px;">📎 ${fileLabel}</span>` : '';
    div.innerHTML = `<div class="avatar">${avatar}</div><div class="text">${text}${badge}</div>`;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

// 3. Индикатор загрузки
function showTyping() {
    const div = document.createElement('div');
    div.classList.add('message', 'bot');
    div.id = 'typing-indicator';
    div.innerHTML = `<div class="avatar"></div><div class="text" style="color:#666;font-style:italic;">Читаю файл и анализирую...</div>`;
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}
function hideTyping() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
}

// 4. Конвертация в Base64
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            // Убираем префикс "data:text/plain;base64,"
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = () => reject(new Error('Не удалось прочитать файл'));
        reader.readAsDataURL(file);
    });
}

// 5. Определение типа
function getFileType(name) {
    const ext = name.split('.').pop().toLowerCase();
    if (['jpg','jpeg','png','gif','webp'].includes(ext)) return 'image';
    if (['pdf','docx','doc','txt'].includes(ext)) return 'text';
    return null;
}

// 6. Отправка
async function sendMessage() {
    if (isSending) return;
    const text = messageInput.value.trim();
    if (!text && !selectedFile) return;

    isSending = true;
    const fileLabel = selectedFile ? selectedFile.name : '';
    addMessage(text || '[Файл]', 'user', fileLabel);

    let payload = { message: text, file: null, fileName: null, fileType: null };

    if (selectedFile) {
        const fType = getFileType(selectedFile.name);
        if (!fType) {
            addMessage('❌ Формат не поддерживается. Используйте PDF, DOCX, TXT, JPG, PNG', 'bot');
            finishSend(); return;
        }
        try {
            console.log('⏳ Конвертация файла в base64...');
            const b64 = await fileToBase64(selectedFile);
            payload.file = b64;
            payload.fileName = selectedFile.name;
            payload.fileType = fType;
            console.log('✅ Файл готов к отправке. Тип:', fType, '| Длина base64:', b64.length);
        } catch (err) {
            console.error('❌ Ошибка чтения файла:', err);
            addMessage('❌ Ошибка: не удалось прочитать файл. Попробуйте другой.', 'bot');
            finishSend(); return;
        }
    }

    console.log(' Отправка payload:', JSON.stringify(payload, null, 2));

    messageInput.value = '';
    resetFileInput();
    showTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        hideTyping();
        addMessage(data.success ? data.message : '❌ ' + data.error, 'bot');
        console.log('📥 Ответ сервера:', data.success ? 'OK' : data.error);
    } catch (err) {
        hideTyping();
        addMessage('❌ Ошибка соединения с сервером', 'bot');
        console.error('🔥 Network error:', err);
    }

    finishSend();
}

function resetFileInput() {
    fileNameEl.style.display = 'none';
    fileNameEl.textContent = '';
    fileInput.value = '';
    selectedFile = null;
}

function finishSend() {
    sendBtn.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
    isSending = false;
}

// Привязка событий
sendBtn.onclick = sendMessage;
messageInput.onkeypress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
};