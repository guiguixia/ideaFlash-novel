import { useEffect, useRef, useState } from 'react'
import { Download, ImagePlus, MessageCircle, Plus, Sparkles, UserPlus, X } from 'lucide-react'
import { kernelDelete, kernelGet, kernelPatch, kernelPost, kernelStreamPost, kernelUpload, kernelUrl } from './lib/kernel-api'

type Script = { id: string; title: string; characters: string[] }
type EmotionSlot = 'default' | 'thinking' | 'puzzled' | 'happy' | 'low' | 'taunting'
type CustomEmotion = { id: string; name: string; description: string; imageUrl: string }
type Card = { id: string; name: string; identity: string; imageUrl: string; emotionImages: Partial<Record<EmotionSlot, string>>; emotionDescriptions: Record<EmotionSlot, string>; customEmotions: CustomEmotion[] }
type Message = { role: 'user' | 'assistant'; content: string; status?: 'generating' | 'failed'; error?: string }
type ChatSummary = { id: string; title: string; turn: number; updatedAt: string | null }
type PlayerProfile = { identity: string; gender: string; age: string; description: string }
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
  { id: 'taunting', title: '嘲讽', hint: '角色轻蔑、戏谑或挑衅时' },
]

export function RoleCardsV2({ workId, scriptId, autoOpenCardId = '' }: { workId: string; scriptId: string; autoOpenCardId?: string }) {
  const [scripts, setScripts] = useState<Script[]>([])
  const [selected, setSelected] = useState(scriptId)
  const [cards, setCards] = useState<Card[]>([])
  const [imageCard, setImageCard] = useState<Card | null>(null)
  const [generationTarget, setGenerationTarget] = useState<{ card: Card; slot: string; title: string; initialDescription: string } | null>(null)
  const [generationDescription, setGenerationDescription] = useState('')
  const [generationReferences, setGenerationReferences] = useState<File[]>([])
  const [generatingImage, setGeneratingImage] = useState(false)
  const [customDraft, setCustomDraft] = useState({ name: '', description: '' })
  const [chatCard, setChatCard] = useState<Card | null>(null)
  const [sessions, setSessions] = useState<ChatSummary[]>([])
  const [chat, setChat] = useState<Chat | null>(null)
  const [input, setInput] = useState('')
  const [editingTitle, setEditingTitle] = useState<string | null>(null)
  const [profileDialog, setProfileDialog] = useState(false)
  const [playerProfile, setPlayerProfile] = useState<PlayerProfile>({ identity: '', gender: '', age: '', description: '' })
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

  useEffect(() => {
    if (!chatCard || busy) return
    let cancelled = false
    const refreshChat = async () => {
      try {
        const rows = await kernelGet<ChatSummary[]>(chatBase)
        if (cancelled) return
        setSessions(rows)
        const selectedId = chat?.id && rows.some((item) => item.id === chat.id) ? chat.id : rows[0]?.id
        if (selectedId) {
          const latest = await kernelGet<Chat>(`${chatBase}/${selectedId}`)
          if (!cancelled) setChat(latest)
        }
      } catch {
        // 后台同步失败不打断用户正在进行的私聊；下一轮轮询会自动重试。
      }
    }
    const timer = window.setInterval(() => void refreshChat(), 2500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [busy, chat?.id, chatBase, chatCard])

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

  const openImageGeneration = (card: Card, slot: string, title: string, initialDescription: string) => {
    setGenerationTarget({ card, slot, title, initialDescription })
    setGenerationDescription(initialDescription)
    setGenerationReferences([])
  }

  const generateImage = async () => {
    if (!generationTarget || !generationDescription.trim() || generationReferences.length < 1) return
    try {
      setGeneratingImage(true)
      setError('')
      const form = new FormData()
      form.append('slot', generationTarget.slot)
      form.append('description', generationDescription.trim())
      generationReferences.forEach((file) => form.append('reference_images', file))
      const updated = await kernelUpload<Card>(`${base}/${generationTarget.card.id}/generate-image`, form)
      replaceCard(updated)
      setGenerationTarget(null)
    } catch (cause) { setError(failure(cause, '角色形象生成失败')) } finally { setGeneratingImage(false) }
  }

  const removeEmotionImage = async (card: Card, slot: EmotionSlot) => {
    try {
      setError('')
      replaceCard(await kernelDelete<Card>(`${base}/${card.id}/image?slot=${slot}`))
    } catch (cause) { setError(failure(cause, '删除图片失败')) }
  }

  const saveEmotionDescription = async (card: Card, slot: EmotionSlot, description: string) => {
    const trimmed = description.trim()
    if (!trimmed) return
    try {
      setError('')
      replaceCard(await kernelPatch<Card>(`${base}/${card.id}/emotion-descriptions/${slot}`, { description: trimmed }))
    } catch (cause) { setError(failure(cause, '保存状态描述失败')) }
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

  const savePlayerProfile = async () => {
    try {
      setBusy(true)
      await kernelPatch<PlayerProfile>('/api/profile', playerProfile)
      setProfileDialog(false)
    } catch (cause) { setError(failure(cause, '保存我的设定失败')) } finally { setBusy(false) }
  }

  const openProfile = async () => {
    try {
      setError('')
      setPlayerProfile(await kernelGet<PlayerProfile>('/api/profile'))
      setProfileDialog(true)
    } catch (cause) { setError(failure(cause, '加载我的设定失败')) }
  }

  const deleteSession = async (target: ChatSummary | Chat | null = chat) => {
    if (!target || !window.confirm(`确认删除「${target.title}」吗？该聊天记录无法恢复。`)) return
    try {
      setBusy(true)
      await kernelDelete(`${chatBase}/${target.id}`)
      const remaining = sessions.filter((item) => item.id !== target.id)
      setSessions(remaining)
      if (chat?.id === target.id) {
        setChat(null)
        if (remaining[0]) await selectSession(remaining[0].id)
      }
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
        <header className="flex items-start justify-between gap-4"><div><p className="text-xs text-brand">角色形象与情绪状态</p><h3 className="mt-1 text-xl font-semibold">{imageCard.name}</h3><p className="mt-1 text-sm text-muted-foreground">已配置 {Object.keys(imageCard.emotionImages).length} 个固定状态；可另新增最多 5 个角色专属状态。</p></div><button onClick={() => setImageCard(null)} aria-label="关闭形象管理" className="rounded-lg p-2 hover:bg-hover"><X className="size-4" /></button></header>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">{emotionSlots.map((slot) => {
          const image = imageCard.emotionImages[slot.id]
          const description = imageCard.emotionDescriptions?.[slot.id] || ''
          return <article key={slot.id} className="overflow-hidden rounded-xl border bg-surface">
            <div className="flex min-h-36 gap-3 p-3">
              {image ? <img src={kernelUrl(image)} alt={slot.title} className="size-20 shrink-0 rounded-lg object-cover" /> : <div className="grid size-20 shrink-0 place-items-center rounded-lg border border-dashed text-muted-foreground"><div className="text-center"><ImagePlus className="mx-auto size-5" /><span className="mt-1 block text-[10px]">悬空</span></div></div>}
              <div className="min-w-0 flex-1"><h4 className="font-medium">{slot.title}{slot.id === 'default' && <span className="ml-2 text-xs text-brand">必填</span>}</h4><p className="mt-1 text-xs leading-5 text-muted-foreground">{slot.hint}</p><textarea value={description} onChange={(event) => setImageCard((current) => current ? { ...current, emotionDescriptions: { ...current.emotionDescriptions, [slot.id]: event.target.value } } : current)} onBlur={(event) => void saveEmotionDescription(imageCard, slot.id, event.currentTarget.value)} maxLength={160} rows={2} className="mt-2 w-full resize-none rounded border bg-workspace px-2 py-1 text-xs leading-5" placeholder="描述该状态下的外貌或神态" aria-label={`${slot.title}形象描述`} /></div>
            </div>
            <div className="flex flex-wrap gap-2 border-t px-3 py-2"><label className="cursor-pointer rounded-md border px-2.5 py-1 text-xs hover:bg-hover">{image ? '替换图片' : '上传图片'}<input hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(imageCard, slot.id, file); event.currentTarget.value = '' }} /></label><button onClick={() => openImageGeneration(imageCard, slot.id, slot.title, description)} className="rounded-md border border-brand-border px-2.5 py-1 text-xs text-brand hover:bg-brand-soft"><Sparkles className="mr-1 inline size-3" />AI 生成</button>{image && <a href={kernelUrl(image)} download={`${imageCard.name}-${slot.title}`} className="rounded-md border px-2.5 py-1 text-xs hover:bg-hover"><Download className="mr-1 inline size-3" />下载</a>}{image && <button onClick={() => void removeEmotionImage(imageCard, slot.id)} className="rounded-md px-2.5 py-1 text-xs text-destructive hover:bg-hover">删除</button>}</div>
          </article>
        })}</div>
        <div className="mt-6 border-t pt-5"><div className="flex items-center justify-between"><div><h4 className="font-medium">角色专属状态</h4><p className="mt-1 text-xs text-muted-foreground">只有配置图片的状态才会在聊天与剧情体验中启用。</p></div><span className="text-xs text-muted-foreground">{imageCard.customEmotions.length}/5</span></div>{imageCard.customEmotions.length ? <div className="mt-3 grid gap-3 sm:grid-cols-2">{imageCard.customEmotions.map((emotion) => <article key={emotion.id} className="overflow-hidden rounded-xl border bg-surface"><div className="flex gap-3 p-3">{emotion.imageUrl ? <img src={kernelUrl(emotion.imageUrl)} alt={emotion.name} className="size-20 shrink-0 rounded-lg object-cover" /> : <div className="grid size-20 shrink-0 place-items-center rounded-lg border border-dashed text-muted-foreground"><div className="text-center"><ImagePlus className="mx-auto size-5" /><span className="mt-1 block text-[10px]">未启用</span></div></div>}<div className="min-w-0 flex-1"><input value={emotion.name} onChange={(event) => setImageCard((current) => current ? { ...current, customEmotions: current.customEmotions.map((item) => item.id === emotion.id ? { ...item, name: event.target.value } : item) } : current)} onBlur={() => void saveCustomEmotion(imageCard, emotion)} maxLength={40} className="w-full rounded border bg-workspace px-2 py-1 text-sm font-medium" placeholder="状态名称" /><textarea value={emotion.description} onChange={(event) => setImageCard((current) => current ? { ...current, customEmotions: current.customEmotions.map((item) => item.id === emotion.id ? { ...item, description: event.target.value } : item) } : current)} onBlur={() => void saveCustomEmotion(imageCard, emotion)} maxLength={160} rows={2} className="mt-2 w-full resize-none rounded border bg-workspace px-2 py-1 text-xs leading-5" placeholder="状态描述，例如：动用异火、战斗爆发时" aria-label={`${emotion.name || '自定义状态'}描述`} /></div></div><div className="flex flex-wrap gap-2 border-t px-3 py-2"><label className="cursor-pointer rounded-md border px-2.5 py-1 text-xs hover:bg-hover">{emotion.imageUrl ? '替换图片' : '上传图片'}<input hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadCustomEmotion(imageCard, emotion, file); event.currentTarget.value = '' }} /></label><button onClick={() => openImageGeneration(imageCard, emotion.id, emotion.name || '自定义状态', emotion.description)} className="rounded-md border border-brand-border px-2.5 py-1 text-xs text-brand hover:bg-brand-soft"><Sparkles className="mr-1 inline size-3" />AI 生成</button><button onClick={() => void deleteCustomEmotion(imageCard, emotion)} className="rounded-md px-2.5 py-1 text-xs text-destructive hover:bg-hover">删除状态</button></div></article>)}</div> : null}{imageCard.customEmotions.length < 5 && <div className="mt-3 grid gap-2 rounded-xl border border-dashed p-3 sm:grid-cols-[1fr_1.5fr_auto]"><input value={customDraft.name} onChange={(event) => setCustomDraft((current) => ({ ...current, name: event.target.value }))} maxLength={40} placeholder="状态名称，例如：灵焰" className="rounded border bg-surface px-2 py-2 text-sm" /><input value={customDraft.description} onChange={(event) => setCustomDraft((current) => ({ ...current, description: event.target.value }))} maxLength={160} placeholder="状态描述，例如：动用异火、战斗爆发时" className="rounded border bg-surface px-2 py-2 text-sm" /><button onClick={() => void createCustomEmotion(imageCard)} disabled={!customDraft.name.trim()} className="rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">新增状态</button></div>}</div>
      </section>
    </div>}

    {generationTarget && <div className="fixed inset-0 z-[80] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !generatingImage) setGenerationTarget(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`AI 生成 ${generationTarget.card.name} 的形象`} className="w-full max-w-xl rounded-[22px] border bg-workspace p-5 shadow-[var(--shadow-floating-strong)]">
        <header className="flex items-start justify-between gap-4"><div><p className="text-xs text-brand">角色形象生成</p><h3 className="mt-1 text-xl font-semibold">{generationTarget.card.name} · {generationTarget.title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">上传 1—3 张人物或服装参考图，生成前仅会使用本角色资料与下方描述。</p></div><button onClick={() => !generatingImage && setGenerationTarget(null)} aria-label="关闭角色形象生成" className="rounded-lg p-2 hover:bg-hover disabled:opacity-50" disabled={generatingImage}><X className="size-4" /></button></header>
        <label className="mt-5 block text-sm">参考图（1—3 张）<input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(event) => { const files = Array.from(event.target.files || []).slice(0, 3); setGenerationReferences(files); event.currentTarget.value = '' }} className="mt-1 block w-full rounded-lg border bg-surface px-3 py-2 text-sm" /></label>
        <p className="mt-2 text-xs text-muted-foreground">{generationReferences.length ? generationReferences.map((file) => file.name).join('、') : '可优先上传正面形象、服装或饰品参考图。'}</p>
        <div className="mt-4 overflow-hidden rounded-xl border text-sm"><label className="grid grid-cols-[132px_minmax(0,1fr)] border-b"><span className="bg-active px-3 py-2.5 font-medium">Character</span><input readOnly value={generationTarget.card.name} className="min-w-0 bg-workspace px-3 py-2.5 text-muted-foreground" /></label><label className="grid grid-cols-[132px_minmax(0,1fr)] border-b"><span className="bg-active px-3 py-2.5 font-medium">Target state</span><input value={generationDescription} onChange={(event) => setGenerationDescription(event.target.value)} maxLength={1600} placeholder="例如：神情威严沉稳，自然站立" className="min-w-0 bg-workspace px-3 py-2.5 outline-none ring-brand focus:ring-1" /></label><label className="grid grid-cols-[132px_minmax(0,1fr)] border-b"><span className="bg-active px-3 py-2.5 font-medium">Reference priority</span><input readOnly value="服饰、饰品、发型与画风严格以参考图为准" className="min-w-0 bg-workspace px-3 py-2.5 text-muted-foreground" /></label><label className="grid grid-cols-[132px_minmax(0,1fr)] border-b"><span className="bg-active px-3 py-2.5 font-medium">Background</span><input readOnly value="透明背景（PNG Alpha），无场景、地面与投影" className="min-w-0 bg-workspace px-3 py-2.5 text-muted-foreground" /></label><label className="grid grid-cols-[132px_minmax(0,1fr)]"><span className="bg-active px-3 py-2.5 font-medium">Strict output rule</span><input readOnly value="禁止所有文字、水印、额外人物、场景与裁切" className="min-w-0 bg-workspace px-3 py-2.5 text-muted-foreground" /></label></div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">补充内容只影响神态、姿势和状态，不会覆盖参考图的服装；实际生成时间通常约 20—45 秒。</p>
        <div className="mt-5 flex justify-end gap-2"><button onClick={() => setGenerationTarget(null)} disabled={generatingImage} className="rounded-lg border px-4 py-2 text-sm hover:bg-hover disabled:opacity-50">取消</button><button onClick={() => void generateImage()} disabled={generatingImage || !generationDescription.trim() || generationReferences.length < 1} className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{generatingImage ? '正在生成…' : '生成并使用'}</button></div>
      </section>
    </div>}

    {chatCard && <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) setChatCard(null) }}>
      <section role="dialog" aria-modal="true" aria-label={`与 ${chatCard.name} 私聊`} className="grid h-[min(720px,calc(100vh-2rem))] w-full max-w-5xl overflow-hidden rounded-[22px] border border-border bg-workspace shadow-[var(--shadow-floating-strong)] md:grid-cols-[230px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r p-3"><div className="flex items-center justify-between gap-2"><div><p className="text-xs text-brand">私聊会话</p><p className="text-sm font-medium">{chatCard.name}</p></div><button onClick={() => setChatCard(null)} aria-label="退出私聊" title="退出私聊" className="rounded-lg p-2 hover:bg-hover"><X className="size-4" /></button></div><button onClick={() => void createSession()} disabled={busy} className="mt-4 inline-flex items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm hover:bg-hover disabled:opacity-50"><Plus className="size-4" />新建会话</button><div className="mt-3 min-h-0 flex-1 space-y-1 overflow-auto">{sessions.map((item) => <div key={item.id} className={`group flex items-center gap-1 rounded-lg ${chat?.id === item.id ? 'bg-active' : 'hover:bg-hover'}`}><button onClick={() => void selectSession(item.id)} className="min-w-0 flex-1 px-3 py-2 text-left"><span className="block truncate text-sm font-medium">{item.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{item.turn} 轮 · {chatTime(item.updatedAt)}</span></button><button onClick={() => void deleteSession(item)} disabled={busy} aria-label={`删除会话 ${item.title}`} title="删除会话" className="mr-1 rounded p-1.5 text-destructive opacity-0 hover:bg-destructive/10 group-hover:opacity-100 focus:opacity-100 disabled:opacity-40"><X className="size-4" /></button></div>)}</div></aside>
        <main className="flex min-h-0 min-w-0 flex-col p-5"><header className="flex items-center justify-between gap-3"><div><p className="text-xs text-brand">副本专属私聊</p>{chat && editingTitle !== null ? <input autoFocus value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} onBlur={() => void renameSession()} onKeyDown={(event) => { if (event.key === 'Enter') void renameSession(); if (event.key === 'Escape') setEditingTitle(null) }} className="mt-1 w-full rounded border bg-surface px-2 py-1 text-lg font-semibold" /> : <h3 onDoubleClick={() => chat && setEditingTitle(chat.title)} title="双击修改名称" className="mt-1 cursor-text text-lg font-semibold">{chat?.title || '选择或新建一个会话'}</h3>}</div><button onClick={() => void openProfile()} disabled={busy} className="rounded-lg px-2 py-1.5 text-sm hover:bg-hover">我的设定</button></header>
          {chat ? <><div ref={messageListRef} className="mt-5 flex-1 space-y-3 overflow-auto">{chat.history.length === 0 ? <p className="rounded-xl bg-active p-4 text-sm text-muted-foreground">向 {chatCard.name} 打个招呼吧。这里的聊天不会推进体验剧情。</p> : chat.history.map((message, index) => <div key={index} className={`whitespace-pre-wrap rounded-xl p-3 text-sm leading-6 ${message.role === 'user' ? 'ml-10 bg-foreground text-primary-foreground' : 'mr-10 bg-active'}`}>{message.role === 'assistant' && !message.content ? (message.status === 'failed' ? <span className="text-destructive">回复失败：{message.error || '请稍后重试。'}</span> : <span className="inline-flex items-center gap-2 text-muted-foreground"><span>{chatCard.name} 正在回复</span><span className="flex gap-1"><i className="size-1.5 animate-bounce rounded-full bg-brand" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:150ms]" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:300ms]" /></span></span>) : <>{message.content}{busy && message.role === 'assistant' && index === chat.history.length - 1 && <span className="ml-2 inline-flex gap-1 align-middle"><i className="size-1.5 animate-bounce rounded-full bg-brand" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:150ms]" /><i className="size-1.5 animate-bounce rounded-full bg-brand [animation-delay:300ms]" /></span>}</>}</div>)}</div><div className="mt-4 flex gap-2"><input value={input} disabled={busy} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void send() }} placeholder={`对 ${chatCard.name} 说点什么…`} className="min-w-0 flex-1 rounded-lg border bg-surface px-3 py-2" /><button onClick={() => void send()} disabled={busy || !input.trim()} className="rounded-lg bg-foreground px-4 text-sm text-primary-foreground disabled:opacity-50">{busy ? '生成中…' : '发送'}</button></div></> : <div className="grid flex-1 place-items-center text-center"><div><p className="text-sm text-muted-foreground">选择左侧历史会话继续聊天，或新建一个会话。</p><button onClick={() => void createSession()} disabled={busy} className="mt-3 rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">新建会话</button></div></div>}
        </main>
      </section>
    </div>}
    {profileDialog && <div className="fixed inset-0 z-[80] grid place-items-center bg-black/45 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setProfileDialog(false) }}><section role="dialog" aria-modal="true" aria-label="我的身份设定" className="w-full max-w-lg rounded-[22px] border bg-workspace p-5 shadow-[var(--shadow-floating-strong)]"><header className="flex items-start justify-between gap-4"><div><p className="text-xs text-brand">应用级设定</p><h3 className="mt-1 text-xl font-semibold">我的身份</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">所有角色私聊都会使用这份设定，角色会据此调整称呼与互动方式；不会影响副本剧情。</p></div><button onClick={() => setProfileDialog(false)} disabled={busy} className="rounded-lg p-2 hover:bg-hover"><X className="size-4" /></button></header><div className="mt-5 grid gap-3 sm:grid-cols-2"><label className="text-sm">身份<input value={playerProfile.identity} onChange={(event) => setPlayerProfile((value) => ({ ...value, identity: event.target.value }))} maxLength={160} placeholder="例如：萧家旁支弟子" className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="text-sm">性别<input value={playerProfile.gender} onChange={(event) => setPlayerProfile((value) => ({ ...value, gender: event.target.value }))} maxLength={40} placeholder="例如：女" className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="text-sm">年龄<input value={playerProfile.age} onChange={(event) => setPlayerProfile((value) => ({ ...value, age: event.target.value }))} maxLength={40} placeholder="例如：16岁" className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label></div><label className="mt-3 block text-sm">补充说明<textarea value={playerProfile.description} onChange={(event) => setPlayerProfile((value) => ({ ...value, description: event.target.value }))} maxLength={800} rows={4} placeholder="例如：与你自幼相识，擅长炼药，对退婚一事有所顾虑。" className="mt-1 w-full resize-none rounded-lg border bg-surface px-3 py-2" /></label><div className="mt-5 flex justify-end gap-2"><button onClick={() => setProfileDialog(false)} disabled={busy} className="rounded-lg border px-4 py-2 text-sm">取消</button><button onClick={() => void savePlayerProfile()} disabled={busy} className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">{busy ? '保存中…' : '保存全局设定'}</button></div></section></div>}
  </section>
}
