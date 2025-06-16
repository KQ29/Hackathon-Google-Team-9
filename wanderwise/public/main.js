const chatDiv = document.getElementById('chat');
const msgInput = document.getElementById('message');
const sendBtn = document.getElementById('send');

function appendBubble(text, isUser) {
  const bubble = document.createElement('div');
  bubble.className = `mb-2 p-2 rounded ${
    isUser ? 'bg-blue-100 self-end' : 'bg-gray-200'
  } max-w-xs`;
  bubble.innerText = text;
  chatDiv.appendChild(bubble);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}

sendBtn.onclick = async () => {
  const message = msgInput.value.trim();
  if (!message) return;
  appendBubble(message, true);
  msgInput.value = '';

  appendBubble('Planning...', false);
  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });
  const { reply } = await res.json();
  chatDiv.removeChild(chatDiv.lastChild);
  appendBubble(reply, false);
};
