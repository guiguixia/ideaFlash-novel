const petWrap = document.querySelector('#petWrap');
const pet = document.querySelector('#pet');
const stage = document.querySelector('.stage');
const speech = document.querySelector('#speech');
const speak = document.querySelector('#speak');
const petImage = document.querySelector('#petImage');
const params = new URLSearchParams(window.location.search);
const characterName = params.get('name') || '角色';
const imageUrl = params.get('image');
const petStatus = document.querySelector('#petStatus');
const stateDescription = document.querySelector('#stateDescription');
const stateAssets = {
  idle: { image: '../../data/tmp/xiaoyan1.jpg', status: '待机中', description: '默认陪伴状态 · 轻微呼吸与浮游', line: '风雪未歇，陪我走一段？' },
  thinking: { image: '../../data/tmp/星夜冰莲沉思-2.png', status: '思考中', description: '回复前的沉思状态 · 浮游放缓、灵光聚拢', line: '让我想想，该从哪里说起。' },
  puzzled: { image: '../../data/tmp/冰莲星夜中的疑惑少年-3.png', status: '有些疑惑', description: '对未知信息的即时反馈 · 轻微侧摆与问号光点', line: '嗯？这件事，我想再确认一下。' },
  flame: { image: '../../data/tmp/掌上冰焰莲-1.png', status: '灵焰相伴', description: '情绪高光状态 · 光晕增强、轨道加速', line: '这份心意，我收下了。' },
};
document.title = `${characterName} · 桌宠动效实验`;
document.querySelector('.pet-name').firstChild.textContent = `${characterName} `;
pet.setAttribute('aria-label', `点击${characterName}互动`);
let activeState = 'idle';
petImage.src = imageUrl || stateAssets.idle.image;
const lines = [`和${characterName}走一段？`, '我会记得你刚才说的话。', '此刻正适合静下心来。', '今天的故事，想从哪里开始？'];
let index = 0;
let dragging = false;
let moved = false;
let origin = { x: 0, y: 0, left: 0, bottom: 0 };

function showSpeech() {
  speech.textContent = index++ === 0 ? stateAssets[activeState].line : lines[index % lines.length];
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

function switchState(nextState) {
  const asset = stateAssets[nextState];
  if (!asset) return;
  activeState = nextState;
  document.body.dataset.petState = nextState;
  petStatus.textContent = `· ${asset.status}`;
  stateDescription.textContent = asset.description;
  petImage.classList.add('is-switching');
  petImage.src = asset.image;
  window.setTimeout(() => petImage.classList.remove('is-switching'), 260);
  document.querySelectorAll('[data-state]').forEach((button) => button.classList.toggle('is-active', button.dataset.state === nextState));
  index = 0;
  showSpeech();
}

document.querySelectorAll('[data-state]').forEach((button) => button.addEventListener('click', () => switchState(button.dataset.state)));

window.setTimeout(showSpeech, 750);
