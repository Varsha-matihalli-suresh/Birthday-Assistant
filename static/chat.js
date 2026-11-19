
const chat = document.getElementById('chat');
const input = document.getElementById('q');
const sendBtn = document.getElementById('sendBtn');

// Display a message in the chat window
function addMessage(text, sender) {
    const message = document.createElement('div');
    message.className = `message ${sender}-message`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'bot' ? '🎂' : '🌸';

    const content = document.createElement('div');
    content.className = 'message-content';

    const name = document.createElement('span');
    name.className = 'message-name';
    name.textContent = sender === 'bot' ? 'Birthday Buddy' : 'You';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;

    content.append(name, bubble);
    message.append(avatar, content);

    chat.appendChild(message);
    message.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// Send the user's question to the Flask backend
async function sendMsg() {
    const text = input.value.trim();

    if (!text) return;

    addMessage(text, 'user');
    input.value = '';
    sendBtn.disabled = true;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: text
            })
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        addMessage(
            data.answer || 'I could not understand the response.',
            'bot'
        );

    } catch (error) {
        console.error('Error:', error);

        addMessage(
            'I could not connect to Birthday Buddy. Please check whether the Flask server is running.',
            'bot'
        );

    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

// Handle quick suggestion buttons
function askSuggestion(text) {
    input.value = text;
    sendMsg();
}

// Send message when Enter is pressed
input.addEventListener('keydown', function(event) {
    if (event.key === 'Enter') {
        sendMsg();
    }
});
