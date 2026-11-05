const petWrap = document.querySelector('#petWrap');
const pet = document.querySelector('#pet');
const stage = document.querySelector('.stage');
const speech = document.querySelector('#speech');
const speak = document.querySelector('#speak');
const petImage = document.querySelector('#petImage');
const params = new URLSearchParams(window.location.search);
const characterName = params.get('name') || '角色';
const imageUrl = params.get('image');
document.title = `${characterName} · 桌宠动效实验`;
document.querySelector('.pet-name').firstChild.textContent = `${characterName} `;
pet.setAttribute('aria-label', `点击${characterName}互动`);
if (imageUrl) petImage.src = imageUrl;
const lines = [`和${characterName}走一段？`, '我会记得你刚才说的话。', '此刻正适合静下心来。', '今天的故事，想从哪里开始？'];
let index = 0;
let dragging = false;
let moved = false;
let origin = { x: 0, y: 0, left: 0, bottom: 0 };

function showSpeech() {
  speech.textContent = lines[index++ % lines.length];
  speech.classList.add('is-visible');
  window.clearTimeout(showSpeech.timer);
  showSpeech.timer = window.setTimeout(() => speech.classList.remove('is-visible'), 4200);
}

pet.addEventListener('click', () => { if (!moved) showSpeech(); });
speak.addEventListener('click', showSpeech);

pet.addEventListener('pointerdown', (event) => {
  dragging = true;
  moved = false;
  const bounds = petWrap.getBoundingClientRect();
  const stageBounds = stage.getBoundingClientRect();
  origin = {
    x: event.clientX,
    y: event.clientY,
    left: bounds.left - stageBounds.left,
    bottom: stageBounds.bottom - bounds.bottom,
  };
  pet.setPointerCapture(event.pointerId);
});
pet.addEventListener('pointermove', (event) => {
  if (!pet.hasPointerCapture(event.pointerId)) return;
  const dx = event.clientX - origin.x;
  const dy = event.clientY - origin.y;
  if (!dragging) return;
  moved ||= Math.abs(dx) + Math.abs(dy) > 2;
  const stageBounds = stage.getBoundingClientRect();
  petWrap.style.left = `${Math.min(stageBounds.width - 80, Math.max(80, origin.left + dx))}px`;
  petWrap.style.bottom = `${Math.min(stageBounds.height - 80, Math.max(-100, origin.bottom - dy))}px`;
  petWrap.style.transform = 'translateX(-50%)';
  event.preventDefault();
});
function releasePet(event) {
  if (pet.hasPointerCapture(event.pointerId)) pet.releasePointerCapture(event.pointerId);
  dragging = false;
}
pet.addEventListener('pointerup', releasePet);
pet.addEventListener('pointercancel', releasePet);

document.querySelectorAll('[data-motion]').forEach((button) => {
  button.addEventListener('click', () => {
    const key = button.dataset.motion;
    const isOn = button.classList.toggle('is-on');
    button.setAttribute('aria-pressed', String(isOn));
    button.textContent = isOn ? 'ON' : 'OFF';
    document.body.classList.toggle(`no-${key}`, !isOn);
  });
});

window.setTimeout(showSpeech, 750);
