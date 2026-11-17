const params = new URLSearchParams(location.search)
const name = params.get('name') || '角色'
const image = params.get('image') || ''
const pet = document.querySelector('#pet')
const imageNode = document.querySelector('#petImage')

document.title = `${name} · 桌宠`
document.querySelector('#petName').textContent = name
imageNode.alt = `${name} 的桌宠形象`
imageNode.src = image
imageNode.addEventListener('error', () => { if (!imageNode.dataset.fallback && image.startsWith('/uploads/')) { imageNode.dataset.fallback = '1'; imageNode.src = `http://127.0.0.1:8004${image}` } })
document.querySelector('#close').addEventListener('click', () => window.close())

pet.addEventListener('dblclick', () => {
  const speech = document.querySelector('#speech')
  speech.textContent = `${name}正在这里陪伴你。`
})

for (const handle of document.querySelectorAll('.resize-handle')) handle.addEventListener('pointerdown', event => {
  const corner = handle.dataset.corner
  let x = event.screenX, y = event.screenY
  handle.setPointerCapture(event.pointerId)
  const move = next => { window.desktopPet?.resize(corner, next.screenX - x, next.screenY - y); x = next.screenX; y = next.screenY }
  handle.addEventListener('pointermove', move)
  handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), { once: true })
})
