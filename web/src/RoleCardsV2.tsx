import { useEffect, useRef, useState } from 'react'
import { ImagePlus, MessageCircle, Plus, Sparkles, Trash2, UserPlus, X } from 'lucide-react'
import { kernelDelete, kernelGet, kernelPatch, kernelPost, kernelStreamPost, kernelUpload, kernelUrl } from './lib/kernel-api'

type Script = { id: string; title: string; characters: string[] }
type EmotionSlot = 'default' | 'thinking' | 'puzzled' | 'happy' | 'low'
type CustomEmotion = { id: string; name: string; description: string; imageUrl: string }
type Card = { id: string; name: string; identity: string; imageUrl: string; emotionImages: Partial<Record<EmotionSlot, string>>; customEmotions: CustomEmotion[] }
type Message = { role: 'user' | 'assistant'; content: string; status?: 'generating' | 'failed'; error?: string }
type ChatSummary = { id: string; title: string; turn: number; updatedAt: string | null }
type Chat = ChatSummary & { history: Message[] }
type Work = { scripts: Script[] }

const failure = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback
const chatTime = (value: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : ''
const emotionSlots: { id: EmotionSlot; title: string; hint: string }[] = [
  { id: 'default', title: '默认形象', hint: '必填 · 未配置状态时的回退图' },
  { id: 'thinking', title: '思考', hint: '发送消息后的等待状态' },
  { id: 'puzzled', title: '疑惑', hint: '角色困惑、不解时' },
  { id: 'happy', title: '开心', hint: '角色愉悦、轻松时' },
  { id: 'low', title: '低落', hint: '角色失落、沉静时' },
]

export function RoleCardsV2({ workId, scriptId, autoOpenCardId = '' }: { workId: string; scriptId: string; autoOpenCardId?: string }) {
  const [scripts, setScripts] = useState<Script[]>([])
  const [selected, setSelected] = useState(scriptId)
  const [cards, setCards] = useState<Card[]>([])
  const [imageCard, setImageCard] = useState<Card | null>(null)
  const [customDraft, setCustomDraft] = useState({ name: '', description: '' })
  const [chatCard, setChatCard] = useState<Card | null>(null)
  const [sessions, setSessions] = useState<ChatSummary[]>([])
  const [chat, setChat] = useState<Chat | null>(null)
  const [input, setInput] = useState('')
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [handledAutoOpen, setHandledAutoOpen] = useState('')
  const messageListRef = useRef<HTMLDivElement>(null)
  const base = `/api/works/${workId}/scripts/${selected}/role-cards`
  const chatBase = chatCard ? `${base}/${chatCard.id}/chats` : ''

  useEffect(() => {
    void kernelGet<Work>(`/api/works/${workId}`).then((work) => {
      setScripts(work.scripts)
      setSelected((current) => work.scripts.some((script) => script.id === current) ? current : work.scripts[0]?.id || '')
    }).catch((cause) => setError(failure(cause, '加载副本失败')))
  }, [workId])

  useEffect(() => {
    if (!selected) return
    setChatCard(null)
    void kernelGet<Card[]>(base).then(setCards).catch((cause) => setError(failure(cause, '加载角色卡失败')))
  }, [base, selected])

  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setChatCard(null) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [])

  useEffect(() => {
    const list = messageListRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [chat?.id, chat?.history])

  const script = scripts.find((item) => item.id === selected)

  const create = async (name: string) => {
    try {
      setError('')
      const card = await kernelPost<Card>(base, { name, identity: '', personality: '', appearance: '', background: '', current_state: '' })
      setCards((current) => [...current, card])
    } catch (cause) { setError(failure(cause, '创建角色卡失败')) }
  }

  const replaceCard = (updated: Card) => {
    setCards((current) => current.map((item) => item.id === updated.id ? updated : item))
    setImageCard((current) => current?.id === updated.id ? updated : current)
  }

  const upload = async (card: Card, slot: EmotionSlot, file: File) => {
    try {
      setError('')
      const form = new FormData()
      form.append('file', file)
      const updated = await kernelUpload<Card>(`${base}/${card.id}/image?slot=${slot}`, form)
      replaceCard(updated)
    } catch (cause) { setError(failure(cause, '图片上传失败')) }
  }

  const removeEmotionImage = async (card: Card, slot: EmotionSlot) => {
    try {
      setError('')
      replaceCard(await kernelDelete<Card>(`${base}/${card.id}/image?slot=${slot}`))
    } catch (cause) { setError(failure(cause, '删除图片失败')) }
  }

  const createCustomEmotion = async (card: Card) => {
    if (!customDraft.name.trim()) return
    try { replaceCard(await kernelPost<Card>(`${base}/${card.id}/custom-emotions`, customDraft)); setCustomDraft({ name: '', description: '' }) } catch (cause) { setError(failure(cause, '新增自定义状态失败')) }
  }

  const saveCustomEmotion = async (card: Card, emotion: CustomEmotion) => {
    try { replaceCard(await kernelPatch<Card>(`${base}/${card.id}/custom-emotions/${emotion.id}`, { name: emotion.name, description: emotion.description })) } catch (cause) { setError(failure(cause, '保存自定义状态失败')) }
  }

  const uploadCustomEmotion = async (card: Card, emotion: CustomEmotion, file: File) => {
    try { const form = new FormData(); form.append('file', file); replaceCard(await kernelUpload<Card>(`${base}/${card.id}/custom-emotions/${emotion.id}/image`, form)) } catch (cause) { setError(failure(cause, '自定义状态图片上传失败')) }
  }

  const deleteCustomEmotion = async (card: Card, emotion: CustomEmotion) => {
    try { replaceCard(await kernelDelete<Card>(`${base}/${card.id}/custom-emotions/${emotion.id}`)) } catch (cause) { setError(failure(cause, '删除自定义状态失败')) }
  }

  const selectSession = async (id: string) => {
    if (!chatBase) return
    try {
      setBusy(true)
      setChat(await kernelGet<Chat>(`${chatBase}/${id}`))
    } catch (cause) { setError(failure(cause, '加载私聊失败')) } finally { setBusy(false) }
  }

  const openChat = async (card: Card) => {
    try {
      setError('')
      setChatCard(card)
      setChat(null)
      setSessions([])
      const cardChatBase = `${base}/${card.id}/chats`
      const rows = await kernelGet<ChatSummary[]>(cardChatBase)
      setSessions(rows)
      if (rows[0]) setChat(await kernelGet<Chat>(`${cardChatBase}/${rows[0].id}`))
    } catch (cause) { setError(failure(cause, '加载私聊会话失败')) }
  }

  useEffect(() => {
    if (!autoOpenCardId || autoOpenCardId === handledAutoOpen) return
    const card = cards.find((item) => item.id === autoOpenCardId)
    if (!card) return
    setHandledAutoOpen(autoOpenCardId)
    void openChat(card)
  }, [autoOpenCardId, handledAutoOpen, cards, base])

  useEffect(() => {
    const openFromPet = (event: MessageEvent<{ type?: string; cardId?: string }>) => {
      if (event.data?.type !== 'story:open-role-chat') return
      const card = cards.find((item) => item.id === event.data.cardId)
      if (card) void openChat(card)
    }
    window.addEventListener('message', openFromPet)
    return () => window.removeEventListener('message', openFromPet)
  }, [cards, base])

  const createSession = async () => {
    if (!chatBase) return
    try {
      setBusy(true)
      const created = await kernelPost<Chat>(chatBase, {})
      setSessions((current) => [created, ...current])
      setChat(created)
    } catch (cause) { setError(failure(cause, '创建私聊失败')) } finally { setBusy(false) }
  }

  const renameSession = async () => {
    if (!chat || !editingTitle?.trim()) return setEditingTitle(null)
    try {
      const updated = await kernelPatch<ChatSummary>(`${chatBase}/${chat.id}`, { title: editingTitle.trim() })
      setSessions((current) => current.map((item) => item.id === updated.id ? { ...item, ...updated } : item))
      setChat((current) => current ? { ...current, ...updated } : current)
    } catch (cause) { setError(failure(cause, '修改会话名称失败')) } finally { setEditingTitle(null) }
  }

  const deleteSession = async () => {
    if (!chat || !window.confirm(`确认删除「${chat.title}」吗？该聊天记录无法恢复。`)) return
    try {
      setBusy(true)
      await kernelDelete(`${chatBase}/${chat.id}`)
      const remaining = sessions.filter((item) => item.id !== chat.id)
      setSessions(remaining)
      setChat(null)
      if (remaining[0]) await selectSession(remaining[0].id)
    } catch (cause) { setError(failure(cause, '删除私聊失败')) } finally { setBusy(false) }
  }

  const send = async () => {
    if (!chat || !input.trim()) return
    const sent = input.trim()
    const optimistic: Message = { role: 'user', content: sent }
    const placeholder: Message = { role: 'assistant', content: '', status: 'generating' }
    try {
      setBusy(true)
      setInput('')
      setChat((current) => current ? { ...current, history: [...current.history, optimistic, placeholder] } : current)
      const updated = await kernelStreamPost<Chat>(`${chatBase}/${chat.id}/turn`, { message: sent }, (chunk) => setChat((current) => current ? { ...current, history: current.history.map((item, index, rows) => index === rows.length - 1 ? { ...item, content: item.content + chunk } : item) } : current))
      setChat(updated)
      setSessions((current) => [{ id: updated.id, title: updated.title, turn: updated.turn, updatedAt: updated.updatedAt }, ...current.filter((item) => item.id !== updated.id)])
    } catch (cause) {
      setChat((current) => current ? { ...current, history: current.history.slice(0, -2) } : current)
      setInput(sent)
      setError(failure(cause, '发送消息失败'))
    } finally { setBusy(false) }
  }

  const openPet = (card: Card) => {
    if (!card.imageUrl) {
      setError('请先上传角色形象，再生成桌宠')
      return
    }
    const url = new URL('./desktop-pet/pet.html', window.location.href)
    url.searchParams.set('name', card.name)
    url.searchParams.set('cardId', card.id)
    url.searchParams.set('image', new URL(kernelUrl(card.imageUrl), window.location.href).toString())
    url.searchParams.set('emotionImages', JSON.stringify(Object.fromEntries(Object.entries(card.emotionImages).map(([slot, image]) => [slot, new URL(kernelUrl(image || ''), window.location.href).toString()]))))
    url.searchParams.set('customEmotionImages', JSON.stringify(Object.fromEntries(card.customEmotions.filter((item) => item.imageUrl).map((item) => [item.id, new URL(kernelUrl(item.imageUrl), window.location.href).toString()]))))
    url.searchParams.set('returnTo', window.location.href)
    url.searchParams.set('workId', workId)
    url.searchParams.set('scriptId', selected)
    url.searchParams.set('apiBase', new URL(kernelUrl('/api'), window.location.href).toString().replace(/\/$/, ''))
    window.open(url.toString(), 'role-pet', 'popup=yes,width=350,height=520')
  }

  return <section className="mx-auto max-w-4xl">
    <header className="rounded-[18px] border bg-workspace p-5">
      <p className="text-xs text-brand">副本专属角色</p><h2 className="mt-1 text-xl font-semibold">角色卡</h2>
      <label className="mt-4 block text-sm">选择副本<select value={selected} onChange={(event) => setSelected(event.target.value)} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2">{scripts.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
    </header>

    {cards.length ? <div className="mt-5 grid gap-3 sm:grid-cols-2">
      {cards.map((card) => <article key={card.id} className="rounded-[18px] border bg-workspace p-4">
        <p className="text-xs text-muted-foreground">所属副本 · {script?.title}</p>
        <div className="mt-3 flex gap-3">{card.imageUrl ? <img src={kernelUrl(card.imageUrl)} alt={`${card.name} 的角色形象`} className="size-16 rounded-xl object-cover" /> : <div className="grid size-16 place-items-center rounded-xl bg-brand-soft text-brand"><ImagePlus /></div>}<div><h3 className="font-semibold">{card.name}</h3><p className="text-sm text-muted-foreground">{card.identity || '尚未补充身份'}</p></div></div>
        <div className="mt-4 flex flex-wrap gap-2"><button onClick={() => setImageCard(card)} className="rounded-lg border px-3 py-1.5 text-sm">管理形象</button><button onClick={() => void openChat(card)} className="rounded-lg border px-3 py-1.5 text-sm"><MessageCircle className="mr-1 inline size-4" />私聊</button><button onClick={() => openPet(card)} className="rounded-lg bg-brand px-3 py-1.5 text-sm text-primary-foreground"><Sparkles className="mr-1 inline size-4" />生成桌宠</button></div>
      </article>)}
    </div> : <section className="mt-5 rounded-[18px] border border-dashed bg-workspace p-7"><h3 className="text-lg font-semibold">这个副本还没有角色卡</h3><p className="mt-2 text-sm text-muted-foreground">可在开始体验选择角色自动创建，或从当前副本抽取的角色中创建。</p><div className="mt-4 flex flex-wrap gap-2">{script?.characters?.map((name) => <button key={name} onClick={() => void create(name)} className="rounded-full border px-3 py-1.5 text-sm"><UserPlus className="mr-1 inline size-4" />{name}</button>)}</div></section>}
    {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

    {imageCard && <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) setImageCard(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`${imageCard.name} 的角色形象与情绪状态`} className="max-h-[min(760px,calc(100vh-2rem))] w-full max-w-3xl overflow-auto rounded-[22px] border bg-workspace p-5 shadow-[var(--shadow-floating-strong)]">
        <header className="flex items-start justify-between gap-4"><div><p className="text-xs text-brand">角色形象与情绪状态</p><h3 className="mt-1 text-xl font-semibold">{imageCard.name}</h3><p className="mt-1 text-sm text-muted-foreground">固定状态 {Object.keys(imageCard.emotionImages).length}/5；可另新增最多 5 个角色专属状态。</p></div><button onClick={() => setImageCard(null)} aria-label="关闭形象管理" className="rounded-lg p-2 hover:bg-hover"><X className="size-4" /></button></header>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">{emotionSlots.map((slot) => { const image = imageCard.emotionImages[slot.id]; return <article key={slot.id} className="overflow-hidden rounded-xl border bg-surface"><div className="flex h-28 items-center gap-3 p-3">{image ? <img src={kernelUrl(image)} alt={slot.title} className="size-20 rounded-lg object-cover" /> : <div className="grid size-20 place-items-center rounded-lg border border-dashed text-muted-foreground"><ImagePlus className="size-5" /></div>}<div className="min-w-0"><h4 className="font-medium">{slot.title}{slot.id === 'default' && <span className="ml-2 text-xs text-brand">必填</span>}</h4><p className="mt-1 text-xs leading-5 text-muted-foreground">{slot.hint}</p></div></div><div className="flex gap-2 border-t px-3 py-2"><label className="cursor-pointer rounded-md border px-2.5 py-1 text-xs hover:bg-hover">{image ? '替换图片' : '上传图片'}<input hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(imageCard, slot.id, file); event.currentTarget.value = '' }} /></label>{image && slot.id !== 'default' && <button onClick={() => void removeEmotionImage(imageCard, slot.id)} className="rounded-md px-2.5 py-1 text-xs text-destructive hover:bg-hover">删除</button>}</div></article> })}</div>
        <div className="mt-6 border-t pt-5"><div className="flex items-center justify-between"><div><h4 className="font-medium">角色专属状态</h4><p className="mt-1 text-xs text-muted-foreground">名称和触发说明会同步给私聊 Prompt；状态可删除。</p></div><span className="text-xs text-muted-foreground">{imageCard.customEmotions.length}/5</span></div>{imageCard.customEmotions.length ? <div className="mt-3 grid gap-3 sm:grid-cols-2">{imageCard.customEmotions.map((emotion) => <article key={emotion.id} className="overflow-hidden rounded-xl border bg-surface"><div className="flex gap-3 p-3">{emotion.imageUrl ? <img src={kernelUrl(emotion.imageUrl)} alt={emotion.name} className="size-20 rounded-lg object-cover" /> : <div className="grid size-20 shrink-0 place-items-center rounded-lg border border-dashed text-muted-foreground"><ImagePlus className="size-5" /></div>}<div className="min-w-0 flex-1"><input value={emotion.name} onChange={(event) => setImageCard((current) => current ? { ...current, customEmotions: current.customEmotions.map((item) => item.id === emotion.id ? { ...item, name: event.target.value } : item) } : current)} onBlur={() => void saveCustomEmotion(imageCard, emotion)} maxLength={40} className="w-full rounded border bg-workspace px-2 py-1 text-sm font-medium" placeholder="状态名称" /><input value={emotion.description} onChange={(event) => setImageCard((current) => current ? { ...current, customEmotions: current.customEmotions.map((item) => item.id === emotion.id ? { ...item, description: event.target.value } : item) } : current)} onBlur={() => void saveCustomEmotion(imageCard, emotion)} maxLength={160} className="mt-2 w-full rounded border bg-workspace px-2 py-1 text-xs" placeholder="何时使用，例如：动用异火时" /></div></div><div className="flex gap-2 border-t px-3 py-2"><label className="cursor-pointer rounded-md border px-2.5 py-1 text-xs hover:bg-hover">{emotion.imageUrl ? '替换图片' : '上传图片'}<input hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadCustomEmotion(imageCard, emotion, file); event.currentTarget.value = '' }} /></label><button onClick={() => void deleteCustomEmotion(imageCard, emotion)} className="rounded-md px-2.5 py-1 text-xs text-destructive hover:bg-hover">删除状态</button></div></article>)}</div> : null}{imageCard.customEmotions.length < 5 && <div className="mt-3 grid gap-2 rounded-xl border border-dashed p-3 sm:grid-cols-[1fr_1.5fr_auto]"><input value={customDraft.name} onChange={(event) => setCustomDraft((current) => ({ ...current, name: event.target.value }))} maxLength={40} placeholder="状态名称，例如：灵焰" className="rounded border bg-surface px-2 py-2 text-sm" /><input value={customDraft.description} onChange={(event) => setCustomDraft((current) => ({ ...current, description: event.target.value }))} maxLength={160} placeholder="触发说明，例如：动用异火、战斗爆发时" className="rounded border bg-surface px-2 py-2 text-sm" /><button onClick={() => void createCustomEmotion(imageCard)} disabled={!customDraft.name.trim()} className="rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">新增状态</button></div>}</div>
      </section>
    </div>}

    {chatCard && <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) setChatCard(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`与 ${chatCard.name} 私聊`} className="grid h-[min(720px,calc(100vh-2rem))] w-full max-w-5xl overflow-hidden rounded-[22px] border border-border bg-workspace shadow-[var(--shadow-floating-strong)] md:grid-cols-[230px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r p-3"><div className="flex items-center justify-between gap-2"><div><p className="text-xs text-brand">私聊会话</p><p className="text-sm font-medium">{chatCard.name}</p></div><button onClick={() => setChatCard(null)} aria-label="关闭私聊" className="rounded-lg p-2 hover:bg-hover"><X className="size-4" /></button></div><button onClick={() => void createSession()} disabled={busy} className="mt-4 inline-flex items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm hover:bg-hover disabled:opacity-50"><Plus className="size-4" />新建会话</button><div className="mt-3 min-h-0 flex-1 space-y-1 overflow-auto">{sessions.map((item) => <button key={item.id} onClick={() => void selectSession(item.id)} className={`w-full rounded-lg px-3 py-2 text-left ${chat?.id === item.id ? 'bg-active' : 'hover:bg-hover'}`}><span className="block truncate text-sm font-medium">{item.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{item.turn} 轮 · {chatTime(item.updatedAt)}</span></button>)}</div></aside>
        <main className="flex min-h-0 min-w-0 flex-col p-5"><header className="flex items-center justify-between gap-3"><div><p className="text-xs text-brand">副本专属私聊</p>{chat && editingTitle !== null ? <input autoFocus value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} onBlur={() => void renameSession()} onKeyDown={(event) => { if (event.key === 'Enter') void renameSession(); if (event.key === 'Escape') setEditingTitle(null) }} className="mt-1 w-full rounded border bg-surface px-2 py-1 text-lg font-semibold" /> : <h3 onDoubleClick={() => chat && setEditingTitle(chat.title)} title="双击修改名称" className="mt-1 cursor-text text-lg font-semibold">{chat?.title || '选择或新建一个会话'}</h3>}</div>{chat && <button onClick={() => void deleteSession()} disabled={busy} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-destructive hover:bg-hover disabled:opacity-50"><Trash2 className="size-4" />删除</button>}</header>
          {chat ? <><div ref={messageListRef} className="mt-5 flex-1 space-y-3 overflow-auto">{chat.history.length === 0 ? <p className="rounded-xl bg-active p-4 text-sm text-muted-foreground">向 {chatCard.name} 打个招呼吧。这里的聊天不会推进体验剧情。</p> : chat.history.map((message, index) => <div key={index} className={`whitespace-pre-wrap rounded-xl p-3 text-sm leading-6 ${message.role === 'user' ? 'ml-10 bg-foreground text-primary-foreground' : 'mr-10 bg-active'}`}>{message.role === 'assistant' && !message.content ? (message.status === 'failed' ? <span className="text-destructive">回复失败：{message.error || '请稍后重试。'}</span> : <span className="inline-flex items-center gap-2 text-muted-foreground"><span>{chatCard.name} 正在回复</span><span className="flex gap-1"><i className="size-1.5 animate-bounce rounded-full bg-brand" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:150ms]" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:300ms]" /></span></span>) : <>{message.content}{busy && message.role === 'assistant' && index === chat.history.length - 1 && <span className="ml-2 inline-flex gap-1 align-middle"><i className="size-1.5 animate-bounce rounded-full bg-brand" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:150ms]" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:300ms]" /></span>}</>}</div>)}</div><div className="mt-4 flex gap-2"><input value={input} disabled={busy} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void send() }} placeholder={`对 ${chatCard.name} 说点什么…`} className="min-w-0 flex-1 rounded-lg border bg-surface px-3 py-2" /><button onClick={() => void send()} disabled={busy || !input.trim()} className="rounded-lg bg-foreground px-4 text-sm text-primary-foreground disabled:opacity-50">{busy ? '生成中…' : '发送'}</button></div></> : <div className="grid flex-1 place-items-center text-center"><div><p className="text-sm text-muted-foreground">选择左侧历史会话继续聊天，或新建一个会话。</p><button onClick={() => void createSession()} disabled={busy} className="mt-3 rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">新建会话</button></div></div>}
        </main>
      </section>
    </div>}
  </section>
}
