
const chat = document.getElementById('chat');
const input = document.getElementById('q');
const sendBtn = document.getElementById('sendBtn');

const micBtn = document.getElementById('micBtn');
const voiceStatus = document.getElementById('voiceStatus');
const speechToggle = document.getElementById('speechToggle');

// ------------------------------------
// 1. VOICE SETTINGS
// ------------------------------------

let speechEnabled = true;
let recognition = null;
let isListening = false;

const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

const speechSupported = 'speechSynthesis' in window;

// ------------------------------------
// 2. DISPLAY CHAT MESSAGES
// ------------------------------------

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

// ------------------------------------
// 3. TEXT-TO-SPEECH
// ------------------------------------


function cleanTextForSpeech(text) {
    return text
        // Remove emojis and their variation characters
        .replace(/\p{Extended_Pictographic}/gu, '')
        .replace(/\uFE0F/g, '')
        // Remove repeated spaces
        .replace(/\s+/g, ' ')
        .trim();
}



function speakResponse(text) {
    if (!speechSupported || !speechEnabled) return;

    window.speechSynthesis.cancel();

    const cleanText = cleanTextForSpeech(text);

    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);

    utterance.lang = 'en-IN';
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    window.speechSynthesis.speak(utterance);
}

// ------------------------------------
// 4. SEND MESSAGE TO FLASK BACKEND
// ------------------------------------

async function sendMsg() {
    const text = input.value.trim();

    if (!text) return;

    // Stop listening before sending
    if (isListening && recognition) {
        recognition.stop();
    }

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

        const answer =
            data.answer || 'I could not understand the response.';

        addMessage(answer, 'bot');

        // Read the response aloud
        speakResponse(answer);

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

// ------------------------------------
// 5. QUICK SUGGESTIONS
// ------------------------------------

function askSuggestion(text) {
    input.value = text;
    sendMsg();
}

// ------------------------------------
// 6. KEYBOARD INPUT
// ------------------------------------

input.addEventListener('keydown', function(event) {
    if (event.key === 'Enter') {
        sendMsg();
    }
});

// ------------------------------------
// 7. SPEECH RECOGNITION SETUP
// ------------------------------------

if (SpeechRecognition) {

    recognition = new SpeechRecognition();

    recognition.lang = 'en-IN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
        isListening = true;

        micBtn.classList.add('listening');
        micBtn.textContent = '⏹️';

        voiceStatus.textContent = 'Listening... Speak now';
    };

    recognition.onresult = function(event) {

        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {

            const transcript = event.results[i][0].transcript;

            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        // Show recognized words in the input
        input.value = finalTranscript || interimTranscript;

        if (finalTranscript) {
            voiceStatus.textContent = 'Speech recognized successfully';
        }
    };

    recognition.onerror = function(event) {

        console.error('Speech recognition error:', event.error);

        const errorMessages = {
            'not-allowed': 'Microphone permission denied',
            'no-speech': 'No speech detected. Try again',
            'audio-capture': 'Microphone not found',
            'network': 'Network error during recognition',
            'aborted': 'Listening stopped'
        };

        voiceStatus.textContent =
            errorMessages[event.error] || 'Voice recognition failed';

    };

    recognition.onend = function() {

        isListening = false;

        micBtn.classList.remove('listening');
        micBtn.textContent = '🎙️';

        if (!voiceStatus.textContent.includes('successfully') &&
            !voiceStatus.textContent.includes('denied') &&
            !voiceStatus.textContent.includes('detected') &&
            !voiceStatus.textContent.includes('found') &&
            !voiceStatus.textContent.includes('error')) {

            voiceStatus.textContent = 'Voice assistant ready';
        }
    };

    // Start / stop microphone
    micBtn.addEventListener('click', function() {

        if (isListening) {
            recognition.stop();
        } else {
            try {
                voiceStatus.textContent = 'Starting microphone...';
                recognition.start();
            } catch (error) {
                console.error(error);
                voiceStatus.textContent = 'Unable to start microphone';
            }
        }
    });

} else {

    micBtn.disabled = true;
    micBtn.title = 'Speech recognition is not supported';

    voiceStatus.textContent =
        'Voice recognition is not supported in this browser';
}

// ------------------------------------
// 8. SPEECH ON / OFF CONTROL
// ------------------------------------

if (speechSupported) {

    speechToggle.addEventListener('click', function() {

        speechEnabled = !speechEnabled;

        if (speechEnabled) {

            speechToggle.textContent = '🔊 Voice ON';

            voiceStatus.textContent = 'Voice assistant ready';

        } else {

            speechToggle.textContent = '🔇 Voice OFF';

            // Stop currently playing speech
            window.speechSynthesis.cancel();
        }
    });

} else {

    speechToggle.disabled = true;
    speechToggle.textContent = 'Voice unavailable';
}
