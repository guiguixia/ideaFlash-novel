const workSelect = document.querySelector('#work')
const chapterSelect = document.querySelector('#chapter')
const roleName = document.querySelector('#roleName')
const message = document.querySelector('#message')
const status = document.querySelector('#status')
const messages = document.querySelector('#messages')
const evidencePanel = document.querySelector('#evidencePanel')
const evidenceList = document.querySelector('#evidenceList')
const send = document.querySelector('#send')
let works = []
let history = []

async function request(path, init = {}) {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers || {}) } })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.code !== 0) throw new Error(payload.msg || payload.detail || `请求失败（HTTP ${response.status}）`)
  return payload.data
}
function option(text, value = '') { return new Option(text, value) }
function resetMessages(text) { history = []; messages.replaceChildren(Object.assign(document.createElement('p'), { className: 'empty', textContent: text })); evidencePanel.hidden = true }
function addBubble(kind, text, loading = false) { const node = document.createElement('p'); node.className = `bubble ${kind}${loading ? ' loading' : ''}`; node.textContent = text; messages.append(node); messages.scrollTop = messages.scrollHeight; return node }
async function loadChapters() {
  const work = works.find(item => item.id === workSelect.value)
  chapterSelect.replaceChildren(option(work ? '正在加载章节…' : '请先选择作品'))
  chapterSelect.disabled = true
  if (!work) { status.textContent = ''; return }
  try {
    const items = await request(`/api/works/${work.id}/chapters`)
    chapterSelect.replaceChildren(...items.map(item => option(`第 ${item.sequence} 章 · ${item.title}`, item.sequence)))
    chapterSelect.disabled = !items.length
    status.textContent = work.ragIndex?.status === 'ready' ? `知识库已就绪，可检索至任意所选章节。` : `该作品知识库状态：${work.ragIndex?.status || '未构建'}。请先在桌面端构建完成后再测试。`
    resetMessages('输入人物名和问题，开始验证角色记忆。')
  } catch (error) { status.textContent = error.message || '章节加载失败'; chapterSelect.replaceChildren(option('章节加载失败')); }
}
async function loadWorks() {
  try {
    works = await request('/api/works')
    const imported = works.filter(item => item.workType !== 'original_story' && item.sourceSegmentCount)
    workSelect.replaceChildren(option(imported.length ? '请选择作品' : '暂无可测试的导入作品'), ...imported.map(item => option(item.title, item.id)))
    workSelect.disabled = !imported.length
    if (!imported.length) status.textContent = '请先在桌面端导入小说并构建角色知识库。'
  } catch (error) { workSelect.replaceChildren(option('作品加载失败')); status.textContent = error.message || '作品加载失败'; }
}
document.querySelector('#chatForm').addEventListener('submit', async event => {
  event.preventDefault()
  const workId = workSelect.value, chapterSequence = Number(chapterSelect.value), name = roleName.value.trim(), content = message.value.trim()
  if (!workId || !chapterSequence || !name || !content) { status.textContent = '请完整选择作品、章节并填写人物名和问题。'; return }
  send.disabled = true; status.textContent = '正在检索角色记忆…'
  addBubble('user', content); message.value = ''
  const pending = addBubble('assistant', `${name}正在回忆原文…`, true)
  try {
    const data = await request('/api/chat', { method: 'POST', body: JSON.stringify({ work_id: workId, chapter_sequence: chapterSequence, role_name: name, message: content, history }) })
    pending.classList.remove('loading'); pending.textContent = data.reply
    history.push({ role: 'user', content }, { role: 'assistant', content: data.reply })
    document.querySelector('#roleLabel').textContent = name
    evidenceList.replaceChildren(...data.evidence.map(item => { const card = document.createElement('article'); card.className = 'evidence-card'; const title = document.createElement('strong'); title.textContent = `第 ${item.chapter} 章 · ${item.title} · 相似度 ${item.score}`; const excerpt = document.createElement('p'); excerpt.textContent = item.content; card.append(title, excerpt); return card }))
    evidencePanel.hidden = false; status.textContent = `已使用 ${data.evidence.length} 条原文证据（模型：${data.model}）。`
  } catch (error) { pending.remove(); status.textContent = error.message || '测试失败'; addBubble('assistant', '本轮实验未能完成，请检查知识库状态与模型配置。') }
  finally { send.disabled = false }
})
workSelect.addEventListener('change', () => void loadChapters())
chapterSelect.addEventListener('change', () => resetMessages('章节已切换；请输入人物名和问题，开始验证角色记忆。'))
roleName.addEventListener('change', () => resetMessages('人物已切换；请输入问题，开始验证角色记忆。'))
void loadWorks()
