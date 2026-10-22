import { useEffect, useState, type FormEvent, type PointerEvent as ReactPointerEvent, type SetStateAction, type WheelEvent } from 'react'
import { HashRouter, Link, Route, Routes, useNavigate, useSearchParams } from 'react-router'
import {
  ArrowLeft,
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  FileText,
  Library,
  ListTodo,
  Loader2,
  LogOut,
  MessageCircle,
  Plus,
  RefreshCw,
  Settings,
  Sparkles,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import {
  isLoggedIn,
  kernelDelete,
  kernelGet,
  kernelPatch,
  kernelPost,
  kernelUpload,
  loginLocal,
  logout,
} from './lib/kernel-api'
import { pickActiveWrittenChapter } from './lib/chapter-view'

type Novel = {
  id: string
  title: string
  genre?: string
  targetPlatform?: string
  targetWords?: number
  writtenWords?: number
  sourceMode: 'writing' | 'script'
  status?: string
  corePromise?: string
  createdAt?: string
  updatedAt?: string
  importedChapterCount?: number
}

type Chapter = {
  id: string
  plotUnitId?: string
  sequence: number
  title: string
  outline?: string
  blueprint?: { summary?: string; protagonistGoal?: string; targetEmotion?: string; keyChoice?: string; characterChange?: string; endingHook?: string; targetWords?: number }
  body?: string
  status: string
  sourceSegmentOrder?: number
  contextPack?: Record<string, unknown>
}

type NovelDetail = Novel & {
  chapters: Chapter[]
  protagonistAgency?: string
  bookSetup?: { targetAudience?: string; logline?: string; coreConflict?: string; genrePositioning?: string; irreplaceableContribution?: string; expectedSettlement?: string; coreAssetsBoundary?: string }
  fullOutline?: FullOutline
  plotUnits?: PlotUnit[]
  plotUnit?: { title?: string; promise?: string; protagonistGoal?: string; obstacle?: string; payoff?: string; forbiddenReveals?: string }
}

type FullOutlineStage = { title: string; chapterRange: string; goal: string; turningPoint: string; forbiddenReveals: string }
type FullOutline = { overview?: string; ending?: string; emotionalCurve?: string; keyHooks?: string; endgameReserves?: string; progressionLadders?: string; stages?: FullOutlineStage[] }
type PlotUnit = { id: string; sequence: number; title: string; promise?: string; protagonistGoal?: string; obstacle?: string; payoff?: string; forbiddenReveals?: string; status?: 'planned' | 'active' | 'completed' | 'archived' }

type Character = {
  id: string
  name: string
  aliases?: string[]
  role?: string
  identity?: string
  importance?: string
  status?: string
  currentState?: string
  firstAppearanceChapter?: number
  modelingStatus?: string
  profile?: Record<string, unknown>
}

type Task = { id: string; type?: string; label?: string; status: string; stage?: string; error?: string; traceId?: string; updatedAt?: string; progress?: number; processedChapters?: number; totalChapters?: number }
type AccountProfile = { id: string; email?: string; username?: string; phone?: string | null; phone_verified?: boolean }

type DialogueMessage = { role: 'user' | 'assistant'; content: string }
type Relationship = { id: string; fromCharacterId?: string; toCharacterId?: string; fromCharacterName?: string; toCharacterName?: string; relationType?: string; currentState?: string; sentiment?: string; sourceEventId?: string; startedChapter?: number; changedChapter?: number }
type Foreshadow = { id: string; title: string; content?: string; status?: string }
type MemoryEvent = { id: string; eventType: string; value: string; quote?: string; validFromSourceSegment?: number; validToSourceSegment?: number | null; evidenceStatus?: string; reviewStatus?: string; knowledgeScope?: string; reviewReason?: string; conflicts?: MemoryEvent[] }
type Candidate = { id: string; name: string; canonicalName?: string; cleaningAction?: string; cleaningConfidence?: number; cleaningReason?: string; mentionSegmentCount?: number; evidenceSnippets?: string[] }
type RevisionSnapshot = { id: string; title: string; body: string; wordCount?: number; reason?: string; createdAt?: string }
type GeneratedDraft = { runId?: string; status?: string; title?: string; body?: string; error?: string }
type WorkbenchGroup = { id: string; label: string; icon: LucideIcon; target: string; unavailable?: boolean; children?: Array<{ id: string; label: string; unavailable?: boolean }> }

function compactExperienceText(value: unknown, fallback = ''): string {
  if (typeof value !== 'string') return fallback
  return value.replace(/\s+/g, ' ').trim()
}

function experienceEventText(event: any): string {
  return compactExperienceText(event?.summary || event?.description || event?.value || event?.title || event?.type)
}

function experienceLocationNames(snapshot: any): string[] {
  return (Array.isArray(snapshot?.locations) ? snapshot.locations : [])
    .map((location: any) => compactExperienceText(location?.name || location?.title || location))
    .filter(Boolean)
    .slice(0, 2)
}

function experienceSynopsis(snapshot: any): string {
  const scenario = snapshot?.scenarioAnalysis?.scenario
  const mainPlot = compactExperienceText(scenario?.main_plot || scenario?.mainPlot)
  if (mainPlot) return mainPlot
  const firstEvent = experienceEventText((snapshot?.events || [])[0])
  if (firstEvent) return firstEvent
  return '这段故事的副本信息正在整理中。'
}

function roleExperienceFacts(card: any, snapshot: any): Array<{ label: string; value: string }> {
  const extracted = (snapshot?.extractedCharacters || []).find((item: any) => item?.name === card?.name)
  const attributes = extracted?.attributes && typeof extracted.attributes === 'object' ? extracted.attributes : {}
  const identity = compactExperienceText(card?.identity || attributes.identity || attributes['身份'])
  const affiliation = compactExperienceText(card?.affiliation || attributes.affiliation || attributes['所属势力'] || attributes['势力'])
  const ability = compactExperienceText(card?.ability || attributes.ability || attributes['能力'] || attributes['实力'] || attributes['修为'])
  const appearance = compactExperienceText(card?.appearance || extracted?.appearance)
  const currentState = compactExperienceText(
    Object.prototype.hasOwnProperty.call(card || {}, 'currentState')
      ? card.currentState
      : attributes.current_state || attributes.currentState || attributes['当前状态'],
  )
  const appearances = Array.isArray(extracted?.sourceSegmentOrders) ? extracted.sourceSegmentOrders : card?.sourceSegmentOrders
  const facts = [
    { label: '身份', value: identity },
    { label: '所属', value: affiliation },
    { label: '能力', value: ability },
    { label: '外貌', value: appearance },
    { label: '当前状态', value: currentState },
  ].filter((fact) => fact.value)
  if (Array.isArray(appearances) && appearances.length) facts.push({ label: '登场', value: `第 ${appearances.slice(0, 2).join('、')} 章` })
  return facts
}

function ExperiencePanel({ novel, initialSnapshotId, enterMode = false, onEnter }: { novel: NovelDetail; initialSnapshotId?: string; enterMode?: boolean; onEnter?: (experienceId: string) => void }) {
  const [start, setStart] = useState(1); const [end, setEnd] = useState(1); const [title, setTitle] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [snapshot, setSnapshot] = useState<any>(null); const [snapshots, setSnapshots] = useState<any[]>([]); const [snapshotQuery, setSnapshotQuery] = useState(''); const [snapshotPage, setSnapshotPage] = useState(1); const [createOpen, setCreateOpen] = useState(false); const [selected, setSelected] = useState<any>(null); const perspective: string = 'third'; const setPerspective = (_value: 'first' | 'third') => undefined; const [session, setSession] = useState<any>(null); const [message, setMessage] = useState(''); const [reply, setReply] = useState(''); const [sessionPage, setSessionPage] = useState(1); const [openingCharacter, setOpeningCharacter] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    if (!session?.id) return
    setSnapshot((current: any) => {
      if (!current || (current.sessions || []).some((item: any) => item.id === session.id)) return current
      return {
        ...current,
        sessions: [{
          id: session.id,
          characterName: session.characterName || selected?.name || '角色对话',
          title: session.title || session.characterName || selected?.name || '角色对话',
          createdAt: session.createdAt || new Date().toISOString(),
          status: session.status || 'active',
          turn: session.turn || 0,
        }, ...(current.sessions || [])],
      }
    })
    onEnter?.(snapshot?.id || initialSnapshotId || '')
  }, [session?.id])
  useEffect(() => {
    if (initialSnapshotId) return
    setSnapshot(null)
    setSelected(null)
    setSession(null)
    setReply('')
  }, [initialSnapshotId])
  useEffect(() => {
    const selectors = Array.from(document.querySelectorAll('select'))
    const perspectiveSelectors = selectors.filter((element) => Array.from(element.options).some((option) => option.textContent?.includes('第一人称')))
    perspectiveSelectors.forEach((element) => { element.style.display = 'none'; element.setAttribute('hidden', 'true'); element.setAttribute('aria-hidden', 'true') })
    return () => perspectiveSelectors.forEach((element) => { element.style.display = ''; element.removeAttribute('hidden'); element.removeAttribute('aria-hidden') })
  }, [snapshot])
  const chapterOptions = [...novel.chapters].sort((a, b) => a.sequence - b.sequence)
  useEffect(() => { if (chapterOptions.length && !chapterOptions.some((item) => item.sequence === start)) { setStart(chapterOptions[0].sequence); setEnd(chapterOptions[0].sequence) } }, [novel.chapters.length])
  useEffect(() => { void kernelGet<any[]>(`/api/novels/${novel.id}/experiences`).then(setSnapshots).catch(() => undefined) }, [novel.id, enterMode])
  useEffect(() => {
    if (!enterMode) return
    if (snapshot?.id) void openSnapshot(snapshot.id)
  }, [enterMode])
  useEffect(() => { if (enterMode && !initialSnapshotId && !snapshot && snapshots.length) { const ready = snapshots.find((item) => item.status === 'ready') || snapshots[0]; if (ready) void openSnapshot(ready.id) } }, [enterMode, initialSnapshotId, snapshot, snapshots])
  useEffect(() => { if (initialSnapshotId) void openSnapshot(initialSnapshotId) }, [initialSnapshotId])
  useEffect(() => {
    if (!snapshot?.id || !session?.id || session.opening) return
    let disposed = false
    let refreshing = false
    const refreshSession = async () => {
      if (disposed || refreshing || document.visibilityState === 'hidden') return
      refreshing = true
      try {
        const data = await kernelGet<any>(`/api/novels/${novel.id}/experiences/${snapshot.id}/sessions/${session.id}`)
        if (disposed) return
        setSession(data)
        setSnapshot((current: any) => current ? { ...current, sessions: (current.sessions || []).map((item: any) => item.id === data.id ? { ...item, turn: data.turn, status: data.status } : item) } : current)
      } catch {
        // 轮询失败不打断当前体验；下一秒会继续尝试同步。
      } finally {
        refreshing = false
      }
    }
    void refreshSession()
    const timer = window.setInterval(() => { void refreshSession() }, 1000)
    return () => { disposed = true; window.clearInterval(timer) }
  }, [novel.id, snapshot?.id, session?.id, session?.opening])
  async function openSnapshot(id: string) { navigate(`/workbench?id=${encodeURIComponent(novel.id)}&section=${enterMode ? 'experience-enter' : 'experience'}&experience=${encodeURIComponent(id)}`); setBusy(true); setError(''); try { const detail = await kernelGet<any>(`/api/novels/${novel.id}/experiences/${id}`); const cards = detail.status === 'ready' ? await kernelGet<any[]>(`/api/novels/${novel.id}/experiences/${id}/role-cards`) : []; setSnapshot({ ...detail, ...detail.snapshot, characters: cards }); const latest = enterMode ? detail.sessions?.[0] : null; if (latest?.id) { const active = await kernelGet<any>(`/api/novels/${novel.id}/experiences/${id}/sessions/${latest.id}`); setSession(active); setSelected(cards.find((card: any) => card.name === active.characterName) || null); const last = [...(active.history || [])].reverse().find((item: any) => item.role === 'assistant'); setReply(last?.content || '') } } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function create() { setBusy(true); setError(''); try { const data = await kernelPost<any>(`/api/novels/${novel.id}/experiences`, { start_source_segment: start, end_source_segment: end, title }); setSnapshot(data); setSelected(null); setSession(null); for (let attempt = 0; attempt < 180; attempt += 1) { await new Promise((resolve) => setTimeout(resolve, 2000)); const detail = await kernelGet<any>(`/api/novels/${novel.id}/experiences/${data.id}`); if (detail.status === 'failed') throw new Error(detail.error || '体验副本创建失败'); if (detail.status === 'ready') { const cards = await kernelGet<any[]>(`/api/novels/${novel.id}/experiences/${data.id}/role-cards`); setSnapshot({ ...data, ...detail, ...detail.snapshot, extractedCharacters: detail.snapshot?.extractedCharacters || [], characters: cards }); setCreateOpen(false); setSnapshots((items) => [{ ...data, status: 'ready' }, ...items.filter((item) => item.id !== data.id)]); break } } } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function enter(card: any) { setSelected(card); setSession({ opening: true, characterName: card.name, history: [{ role: 'assistant', content: `正在生成 ${card.name} 的副本开场…` }] }); setOpeningCharacter(card.name); onEnter?.(snapshot.id); setBusy(true); setError(''); try { const data = await kernelPost<any>(`/api/novels/${novel.id}/experiences/${snapshot.id}/sessions`, { character_id: card.id || undefined, character_name: card.name, role_mode: card.roleMode || 'replacement', perspective: 'third' }); setSnapshot((current: any) => current ? { ...current, sessions: [{ id: data.id, characterName: data.characterName || card.name, title: data.title || data.characterName || card.name, createdAt: data.createdAt || new Date().toISOString(), status: data.status || 'active', turn: data.turn || 0 }, ...(current.sessions || []).filter((item: any) => item.id !== data.id)] } : current); setSession({ ...data, opening: false, history: data.opening ? [{ role: 'assistant', content: data.opening }] : [] }); setReply(data.opening || '') } catch (err) { setError(messageFrom(err)); setSession((current: any) => current?.opening ? null : current) } finally { setBusy(false); setOpeningCharacter('') } }
  async function send(event: FormEvent) { event.preventDefault(); if (!session || session.opening || !message.trim()) return; const current = message; setMessage(''); setBusy(true); try { const data = await kernelPost<any>(`/api/novels/${novel.id}/experiences/${snapshot.id}/sessions/${session.id}/turn`, { message: current }); const reply = data.reply || ''; setReply(reply); setSession((active: any) => active?.id === session.id ? { ...active, turn: data.turn ?? active.turn, history: [...(active.history || []), { role: 'user', content: current }, { role: 'assistant', content: reply }] } : active); setSnapshot((currentSnapshot: any) => currentSnapshot ? { ...currentSnapshot, sessions: (currentSnapshot.sessions || []).map((item: any) => item.id === session.id ? { ...item, turn: data.turn ?? (item.turn || 0) + 1 } : item) } : currentSnapshot) } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  const cards = snapshot?.characters || snapshot?.extractedCharacters || []
  async function openSession(sessionId: string) { try { const data = await kernelGet<any>(`/api/novels/${novel.id}/experiences/${snapshot.id}/sessions/${sessionId}`); setSession(data); setSelected(cards.find((card: any) => card.name === data.characterName) || null); const last = [...(data.history || [])].reverse().find((item: any) => item.role === 'assistant'); setReply(last?.content || '') } catch (err) { setError(messageFrom(err)) } }
  const locations = experienceLocationNames(snapshot)
  const events = (snapshot?.events || []).map(experienceEventText).filter(Boolean).slice(0, 3)
  return <section className={`experience-panel grid grid-cols-[280px_minmax(0,1fr)] items-start gap-5 ${enterMode ? "enter-mode" : ""}`}><div className="rounded-[18px] border border-border bg-workspace p-6"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">已有体验副本</h2><button onClick={() => setCreateOpen(true)} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground">创建副本</button></div><div className="mt-4"><input value={snapshotQuery} onChange={(e) => { setSnapshotQuery(e.target.value); setSnapshotPage(1) }} placeholder="搜索副本名称" className="w-full rounded-lg border bg-surface px-3 py-2 text-sm" /></div><div className="mt-3 grid gap-2 md:grid-cols-2">{snapshots.filter((item) => !snapshotQuery.trim() || String(item.title || '').toLowerCase().includes(snapshotQuery.trim().toLowerCase())).slice((snapshotPage - 1) * 10, snapshotPage * 10).map((item) => <button key={item.id} onClick={() => void openSnapshot(item.id)} className={`rounded-xl border p-3 text-left transition-colors ${snapshot?.id === item.id ? 'border-brand-border bg-brand-soft' : 'border-border hover:bg-hover'}`}><p className="text-sm font-medium">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">第{item.startSourceSegment}—{item.endSourceSegment}章 · {item.status === 'ready' ? '已就绪' : item.status === 'failed' ? '创建失败' : '处理中'}</p><p className="mt-2 text-xs text-muted-foreground">{item.status === 'ready' ? '进入这段故事，选择一个角色开始体验。' : item.status === 'failed' ? '副本未能完成构建。' : '正在整理角色、事件与场景。'}</p></button>)}</div>{!snapshots.length ? <p className="mt-4 text-sm text-muted-foreground">暂无体验副本。</p> : null}<div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>共 {snapshots.filter((item) => !snapshotQuery.trim() || String(item.title || '').toLowerCase().includes(snapshotQuery.trim().toLowerCase())).length} 个</span><div className="flex gap-2"><button disabled={snapshotPage <= 1} onClick={() => setSnapshotPage((page) => page - 1)} className="rounded border border-border px-2 py-1 disabled:opacity-40">上一页</button><button disabled={snapshotPage * 10 >= snapshots.filter((item) => !snapshotQuery.trim() || String(item.title || '').toLowerCase().includes(snapshotQuery.trim().toLowerCase())).length} onClick={() => setSnapshotPage((page) => page + 1)} className="rounded border border-border px-2 py-1 disabled:opacity-40">下一页</button></div></div></div>{createOpen ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"><div className="w-full max-w-2xl rounded-[18px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"><div className="mb-4 flex items-center justify-between"><h1 className="text-xl font-semibold">创建局部体验副本</h1><button onClick={() => setCreateOpen(false)} className="rounded-lg px-2 py-1 text-sm hover:bg-hover">关闭</button></div><p className="mt-2 text-sm text-muted-foreground">选择连续章节（最多30章），系统只基于这段正文建立副本角色和事件，不修改原小说正史。</p><div className="mt-5 grid gap-3 sm:grid-cols-3"><label className="text-sm">开始章节<select value={start} onChange={(e) => { const value = Number(e.target.value); setStart(value); setEnd((current) => Math.max(value, Math.min(current, value + 29))) }} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2">{chapterOptions.map((chapter) => <option key={chapter.id} value={chapter.sequence}>第{chapter.sequence}章 · {chapter.title}</option>)}</select></label><label className="text-sm">结束章节<select value={end} onChange={(e) => setEnd(Number(e.target.value))} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2">{chapterOptions.filter((chapter) => chapter.sequence >= start && chapter.sequence <= start + 29).map((chapter) => <option key={chapter.id} value={chapter.sequence}>第{chapter.sequence}章 · {chapter.title}</option>)}</select></label><label className="text-sm">副本名称<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="可选" className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label></div><button onClick={() => void create()} disabled={busy || !chapterOptions.length || end < start || end - start >= 30} className="mt-4 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{busy ? '处理中…' : '创建副本并抽取角色'}</button>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</div></div> : null}{snapshot ? <div className="rounded-[18px] border border-border bg-workspace p-6"><header className="border-b border-border pb-5"><p className="text-xs font-medium text-brand">局部体验副本</p><div className="mt-1 flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-xl font-semibold">{snapshot.title}</h2><p className="text-xs text-muted-foreground">第 {snapshot.startSourceSegment}—{snapshot.endSourceSegment} 章</p></div><p className="mt-3 max-w-3xl text-sm leading-6 text-body-foreground">{experienceSynopsis(snapshot)}</p><div className="mt-4 flex flex-wrap gap-2 text-xs">{locations.map((location) => <span key={location} className="rounded-full bg-active px-2.5 py-1 text-muted-foreground">地点 · {location}</span>)}<span className="rounded-full bg-active px-2.5 py-1 text-muted-foreground">已准备 {cards.length} 位可体验角色</span>{snapshot.sessions?.length ? <span className="rounded-full bg-active px-2.5 py-1 text-muted-foreground">{snapshot.sessions.length} 段进行中的体验</span> : null}</div>{events.length ? <div className="mt-4 border-l-2 border-brand-border pl-3"><p className="text-xs font-medium text-muted-foreground">本段关键事件</p><p className="mt-1 text-sm leading-6 text-body-foreground">{events.join(' · ')}</p></div> : null}</header><div className="mt-5"><div className="flex items-end justify-between gap-3"><div><h3 className="font-semibold">选择进入角色</h3><p className="mt-1 text-xs text-muted-foreground">角色资料仅说明其在当前副本中已确认的状态。</p></div><p className="text-xs text-muted-foreground">已抽取 {cards.length} 个角色</p></div><div className="mt-4 grid gap-3 md:grid-cols-2">{cards.map((card: any, index: number) => { const facts = roleExperienceFacts(card, snapshot); return <div key={`${card.name}-${index}`} className={`rounded-xl border p-4 text-left ${selected?.name === card.name ? 'border-2 border-black bg-active' : 'border-border'}`}><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{card.name}</p><p className="mt-1 text-xs text-muted-foreground">{card.source === 'chapter_extraction' ? '副本登场角色' : '原著角色'}</p></div><span className="rounded-full bg-active px-2 py-1 text-[11px] text-muted-foreground">{card.role || '人物'}</span></div>{facts.length ? <dl className="mt-3 space-y-1.5 text-xs leading-5 text-body-foreground">{facts.map((fact) => <div key={fact.label} className="flex gap-2"><dt className="shrink-0 text-muted-foreground">{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl> : <p className="mt-3 text-xs leading-5 text-muted-foreground">该角色的副本内状态尚未形成明确描述。</p>}<div className="mt-4 flex justify-end gap-2"><button type="button" onClick={(event) => { event.stopPropagation(); void enter(card) }} className="rounded-md bg-foreground px-2.5 py-1.5 text-xs text-primary-foreground">以此角色进入</button></div></div> })}</div></div></div> : null}{snapshot ? <div className="mt-4 rounded-xl border border-border bg-surface p-3"><p className="mb-1 text-sm font-semibold">{snapshot?.title || "当前副本"}</p><p className="mb-2 text-xs font-medium text-muted-foreground">当前副本对话</p><div className="flex flex-wrap gap-2">{(snapshot?.sessions || []).slice((sessionPage - 1) * 10, sessionPage * 10).map((item: any) => <div key={item.id} className={`relative rounded-md border ${session?.id === item.id ? "border-2 border-black bg-active" : "border-transparent hover:bg-hover"}`}><button onClick={() => void openSession(item.id)} className="w-full px-2 py-1 text-left text-xs"><span className="block truncate pr-4">{item.title || item.characterName || "角色对话"} · 第{item.turn || 0}轮</span><span className="block text-[10px] text-muted-foreground">{item.createdAt ? new Date(item.createdAt).toLocaleString() : ""}</span></button><button title="删除对话" onClick={async (event) => { event.stopPropagation(); if (!window.confirm("永久删除此对话？")) return; await kernelDelete(`/api/novels/${novel.id}/experiences/${snapshot.id}/sessions/${item.id}`); setSnapshot((current: any) => current ? { ...current, sessions: (current.sessions || []).filter((entry: any) => entry.id !== item.id) } : current); if (session?.id === item.id) { setSession(null); setReply("") } }} className="absolute right-1 top-1 rounded p-0.5 text-destructive hover:bg-destructive/10">×</button></div>)}</div></div> : null}{session ? <div className="rounded-[18px] border border-border bg-workspace p-6"><p className="font-semibold">正在体验：{selected?.name}</p><p className="mt-1 text-xs text-muted-foreground">{perspective === 'first' ? '第一人称' : '第三人称'} · 临时体验不会写入正史</p>{(session?.history || []).length ? <div className="mt-5 space-y-3">{session.history.map((item: any, index: number) => <div key={index} className={`whitespace-pre-wrap rounded-xl p-4 text-sm leading-7 ${item.role === "user" ? "ml-8 bg-foreground text-primary-foreground" : "bg-active"}`}>{item.content}</div>)}</div> : <p className="mt-5 text-sm text-muted-foreground">输入一个动作或选择，开始推进副本。</p>}<form onSubmit={send} className="mt-5 flex gap-2"><input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="描述你的动作或对白…" className="min-w-0 flex-1 rounded-lg border bg-surface px-3 py-2.5" /><button disabled={busy || !message.trim()} className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">发送</button></form></div> : null}</section>
}

function formatWords(value?: number) {
  const words = value || 0
  return words >= 10000 ? `${(words / 10000).toFixed(words >= 100000 ? 0 : 1).replace('.0', '')}万字` : `${words.toLocaleString()}字`
}

function chapterStatusLabel(status: string) {
  return ({
    planned: '待生成',
    drafting: '生成中',
    ready_for_author: '待作者审阅',
    accepted: '已采纳',
    rejected: '未采纳',
    failed: '生成失败',
    '待生成': '待生成',
    '生成中': '生成中',
    '草稿生成中': '草稿生成中',
    '待作者审阅': '待作者审阅',
    '已采纳': '已采纳',
    '未采纳': '未采纳',
    '生成失败': '生成失败',
  } as Record<string, string>)[status] || '未知状态'
}

const statusText: Record<string, string> = {
  importing: '导入中',
  imported: '已导入',
  active: '进行中',
  ready: '已就绪',
  planned: '待规划',
  drafting: '草稿生成中',
  ready_for_author: '待作者审阅',
  accepted: '已采纳',
  rejected: '未采纳',
  pending: '待处理',
  queued: '等待执行',
  running: '执行中',
  processing: '处理中',
  succeeded: '已完成',
  completed: '已完成',
  failed: '失败',
  cancelled: '已停止',
  cancel_requested: '正在停止',
  import_failed: '导入失败',
  script_ready: '已就绪',
  archived: '已归档',
  progressing: '推进中',
  resolved: '已解决',
  ignored: '已忽略',
  verified: '已验证',
  weak: '证据较弱',
  unknown: '待核实',
  objective_canon: '客观正史',
  character_known: '人物已知',
  character_modeling: '建立人物档案',
  modeling: '建立档案中',
  modelled: '已建立档案',
  modeled: '已建立档案',
  high: '重要人物',
  medium: '主要人物',
  low: '一般人物',
}

const memoryEventTypeText: Record<string, string> = {
  identity: '身份', background: '背景', goal: '目标', personality: '性格表现', belief: '信念',
  attitude: '态度', relationship: '人物关系', cultivation: '修为', technique: '功法技能',
  weapon: '武器', possession: '持有物', affiliation: '所属势力', status: '状态',
  important_experience: '重要经历', turning_point: '关键转折',
}

function displayStatus(status?: string, fallback = '未知状态') { return statusText[status || ''] || fallback }
function displayMemoryEventType(type?: string) { return memoryEventTypeText[type || ''] || '人物事实' }

const taskStatusText: Record<string, string> = { queued: '等待执行', running: '执行中', succeeded: '已完成', failed: '执行失败', cancelled: '已停止', cancel_requested: '正在停止' }
const taskStageText: Record<string, string> = {
  upload_received: '已接收文件', parsing_source: '解析正文', persisting_chapters: '保存章节', candidate_indexing: '抽取人物候选', candidate_cleaning: '清洗人物候选', candidate_names_ready: '候选人物已就绪', character_selection: '筛选重要人物', character_modeling: '建立人物档案', character_indexing: '建立人物索引', chapter_memory_reindex: '重新索引人物事实', post_analysis_candidate_cleaning: '整理人物候选', index_ready: '索引已就绪', completed: '已完成', failed: '执行失败', cancelled: '已停止', cancel_requested: '正在停止', chapter_revision: 'AI 章节修订', deslop: '去 AI 味', chapter_review: '多视角审稿', sample_indexing: '建立样本索引', chapter_analysis: '分析章节',
}
const taskTypeText: Record<string, string> = { import_analysis: '导入分析', character_modeling: '人物建模', character_index: '人物索引', chapter_revision: 'AI 章节修订', deslop: '去 AI 味', chapter_review: '多视角审稿' }
function displayTaskStatus(status?: string) { return taskStatusText[status || ''] || displayStatus(status) }
function displayTaskStage(stage?: string) { return taskStageText[stage || ''] || displayStatus(stage, '') }
function displayTaskType(type?: string) { return taskTypeText[type || ''] || '后台任务' }
function displayReviewVerdict(verdict?: string) { return ({ APPROVE: '通过', CONCERNS: '需要关注', REJECT: '建议修改' } as Record<string, string>)[verdict || ''] || verdict || '' }

function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

function Unavailable({ title, description }: { title: string; description: string }) {
  return (
    <section className="mx-auto flex min-h-[420px] max-w-xl flex-col items-center justify-center rounded-[22px] border border-dashed border-border bg-surface px-8 text-center">
      <CircleDashed className="mb-4 size-8 text-muted-foreground" />
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
      <span className="mt-5 rounded-full border border-brand-border bg-brand-soft px-3 py-1 text-xs font-medium text-foreground">暂未开放</span>
    </section>
  )
}

function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('ideaFlash')
  const [password, setPassword] = useState('ideaFlash')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError('')
    try {
      if (!username.trim() || !password) throw new Error('请输入管理员账号和密码')
      await loginLocal(username.trim(), password)
      onLoggedIn()
    } catch (err) {
      setError(messageFrom(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="flex min-h-full items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-[390px] rounded-[22px] border border-border bg-workspace p-8 shadow-[var(--shadow-floating)]">
        <div className="mb-7 flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-brand text-lg font-bold text-brand-foreground">N</span>
          <div>
            <h1 className="text-lg font-semibold">Novel</h1>
            <p className="text-xs text-muted-foreground">小说创作与剧本对话</p>
          </div>
        </div>
        <label className="mb-4 block text-sm font-medium">
          管理员账号
          <input value={username} onChange={(e) => setUsername(e.target.value)} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5 outline-none ring-brand focus:ring-2" autoComplete="username" />
        </label>
        <label className="block text-sm font-medium">
          密码
          <input value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5 outline-none ring-brand focus:ring-2" type="password" autoComplete="current-password" />
        </label>
        {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}
        <button
          disabled={pending}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-foreground px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {pending ? <Loader2 className="size-4 animate-spin" /> : null}
          登录
        </button>
        <p className="mt-3 text-center text-xs text-muted-foreground">独立仓库本地管理员登录</p>
      </form>
    </main>
  )
}

function AccountSettingsPage({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<AccountProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function reload() {
    setLoading(true); setError('')
    try {
      setProfile(await kernelGet<AccountProfile>('/api/auth/me'))
    } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) }
  }

  useEffect(() => { void reload() }, [])
  return <main className="mx-auto min-h-full max-w-3xl p-6"><div className="mb-6 flex items-center justify-between"><button onClick={() => navigate('/')} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm hover:bg-hover"><ArrowLeft className="size-4" />返回书架</button><button onClick={() => { logout(); onLogout() }} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-destructive hover:bg-hover"><LogOut className="size-4" />退出登录</button></div><section className="rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-workspace)]"><p className="text-sm text-muted-foreground">账户设置</p><h1 className="mt-1 text-2xl font-semibold">本地管理员</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">Novel 使用独立仓库的本地管理员账号，不依赖其他服务。</p>{loading ? <p className="mt-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />正在读取账户信息…</p> : <div className="mt-6 grid gap-3 sm:grid-cols-2"><div className="rounded-xl bg-active p-4"><p className="text-xs text-muted-foreground">账号</p><p className="mt-1 break-all text-sm font-medium">{profile?.username || 'admin'}</p></div><div className="rounded-xl bg-active p-4"><p className="text-xs text-muted-foreground">用户 ID</p><p className="mt-1 break-all text-sm font-medium">{profile?.id || 'local-admin'}</p></div></div>}{error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}</section></main>
}

function CreateDialog({ mode, onClose, onCreated }: { mode: 'writing' | 'script'; onClose: () => void; onCreated: (novel: Novel) => void }) {
  const [title, setTitle] = useState('')
  const [genre, setGenre] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault(); setPending(true); setError('')
    try {
      if (mode === 'writing') {
        const novel = await kernelPost<Novel>('/api/novels', { title, genre, target_platform: '番茄', target_words: 200000, core_promise: '', protagonist_agency: '', plot_unit_title: '第一个剧情单元', plot_unit_promise: '', protagonist_goal: '', obstacle: '', payoff: '', forbidden_reveals: '' })
        onCreated(novel)
      } else {
        if (!file) throw new Error('请选择要导入的小说文件')
        const form = new FormData(); form.append('file', file); form.append('title', title); form.append('genre', genre); form.append('import_mode', 'script')
        const novel = await kernelUpload<Novel>('/api/novels/import', form)
        onCreated(novel)
      }
    } catch (err) { setError(messageFrom(err)) } finally { setPending(false) }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"><form onSubmit={submit} className="w-full max-w-lg rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"><div className="flex items-start justify-between"><div><h2 className="text-lg font-semibold">{mode === 'writing' ? '新建小说' : '导入剧本'}</h2><p className="mt-1 text-sm text-muted-foreground">{mode === 'writing' ? '创建后进入写作工作台。' : '导入已有小说，自动建立人物记忆并支持角色对话。'}</p></div><button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-hover"><X className="size-5" /></button></div><label className="mt-5 block text-sm font-medium">书名<input required value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5 outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">题材<input value={genre} onChange={(e) => setGenre(e.target.value)} placeholder="玄幻、都市、悬疑…" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5 outline-none focus:ring-2 focus:ring-brand" /></label>{mode === 'script' ? <label className="mt-4 block text-sm font-medium">正文文件<input required type="file" accept=".txt,.md,.zip" onChange={(e) => setFile(e.target.files?.[0] || null)} className="mt-1.5 block w-full rounded-lg border bg-surface p-2 text-sm" /></label> : null}{error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}<div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm hover:bg-hover">取消</button><button disabled={pending} className="flex items-center gap-2 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">{pending ? <Loader2 className="size-4 animate-spin" /> : null}{mode === 'writing' ? '创建并进入' : '开始导入'}</button></div></form></div>
}

function CanonPanel({ detail, characters, memoryFocusNames = [], onChanged, view = 'facts' }: { detail: NovelDetail; characters: Character[]; memoryFocusNames?: string[]; onChanged: () => Promise<void>; view?: 'write' | 'facts' }) {
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [foreshadows, setForeshadows] = useState<Foreshadow[]>([])
  const [outline, setOutline] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pendingChapter = detail.chapters.find((chapter) => ['drafting', 'ready_for_author'].includes(chapter.status))
  const acceptedChapters = detail.chapters.filter((chapter) => chapter.status === 'accepted')
  const plannedChapter = detail.chapters.find((chapter) => chapter.status === 'planned' && chapter.sequence === (acceptedChapters.at(-1)?.sequence || 0) + 1)

  async function reloadCanon() {
    try {
      const [relations, activeClues, progressingClues, plannedClues] = await Promise.all([
        kernelGet<Relationship[]>(`/api/novels/${detail.id}/relationships`),
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows`),
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows?status=progressing`),
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows?status=planned`),
      ])
      setRelationships(relations)
      setForeshadows([...activeClues, ...progressingClues, ...plannedClues])
    } catch (err) { setError(messageFrom(err)) }
  }
  useEffect(() => { void reloadCanon() }, [detail.id])
  async function generate() {
    setBusy(true); setError('')
    try {
      const hasAccepted = acceptedChapters.length > 0
      if (plannedChapter) await kernelPost(`/api/novels/${detail.id}/chapters/${plannedChapter.id}/generate`, { target_words: 1800, memory_focus: memoryFocusNames })
      else await kernelPost(`/api/novels/${detail.id}/chapters/${hasAccepted ? 'next' : 'first'}/generate`, { title: '', outline, target_words: 1800, memory_focus: memoryFocusNames })
      await onChanged()
    } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function accept() {
    if (!pendingChapter) return
    if (!window.confirm(`采纳后，第${pendingChapter.sequence}章正文将锁定，暂不允许手动修改。确定采纳？`)) return
    setBusy(true); setError('')
    try { await kernelPost(`/api/novels/${detail.id}/chapters/${pendingChapter.id}/accept`); await onChanged(); await reloadCanon() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function clueAction(id: string, action: 'ignore' | 'resolve' | 'restore') {
    try { await kernelPost(`/api/novels/${detail.id}/foreshadows/${id}/${action}`); await reloadCanon() } catch (err) { setError(messageFrom(err)) }
  }
  if (view === 'write') return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-muted-foreground">下一步创作</p><h1 className="mt-1 text-lg font-semibold">写下一章</h1><p className="mt-1 text-sm text-muted-foreground">优先使用已准备好的章节细纲；没有细纲时，也可以直接说明这章想发生什么。</p></div>{busy ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}</div>{plannedChapter ? <div className="mt-5 rounded-xl border border-brand-border bg-brand-soft p-4"><p className="text-sm font-medium">将按第 {plannedChapter.sequence} 章《{plannedChapter.title}》细纲生成</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{plannedChapter.blueprint?.summary || plannedChapter.outline}</p></div> : <label className="mt-5 block text-sm font-medium">这一章要发生什么？<textarea value={outline} onChange={(e) => setOutline(e.target.value)} placeholder="例如：主角准备进入遗迹，却发现同行者隐瞒了关键信息…" className="mt-2 min-h-28 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label>}{memoryFocusNames.length ? <p className="mt-3 rounded-lg bg-brand-soft px-3 py-2 text-xs text-muted-foreground">这章会重点承接：{memoryFocusNames.join('、')}</p> : null}<div className="mt-4 flex flex-wrap gap-2"><button disabled={busy} onClick={() => void generate()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{plannedChapter ? '按细纲生成草稿' : acceptedChapters.length ? '生成下一章草稿' : '生成第一章草稿'}</button>{pendingChapter ? <button disabled={busy} onClick={() => void accept()} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">采纳草稿为正文</button> : null}</div>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</div></section>
  return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-muted-foreground">已发生的内容</p><h1 className="mt-1 text-lg font-semibold">故事事实</h1><p className="mt-1 text-sm text-muted-foreground">这里记录已采纳章节带来的关系、伏笔和线索变化，是后续写作的一致性依据。</p></div>{busy ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}</div>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</div><div className="grid gap-5 lg:grid-cols-2"><RelationshipManager novelId={detail.id} relationships={relationships} characters={characters} onChanged={reloadCanon} /><section className="rounded-[18px] border border-border bg-workspace p-5"><h2 className="font-semibold">伏笔与线索</h2><div className="mt-4 space-y-2">{foreshadows.map((item) => <article key={item.id} className="rounded-xl bg-active p-3 text-sm"><p className="font-medium">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">{item.content || item.status || '暂无内容'}</p><div className="mt-3 flex gap-2"><button onClick={() => void clueAction(item.id, 'ignore')} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-hover">忽略</button><button onClick={() => void clueAction(item.id, 'resolve')} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-hover">解决</button></div></article>)}{foreshadows.length === 0 ? <p className="text-sm text-muted-foreground">暂无伏笔与线索。</p> : null}</div></section></div></section>
}

function RelationshipsPanel({ detail, characters }: { detail: NovelDetail; characters: Character[] }) {
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [error, setError] = useState('')
  async function reloadRelationships() {
    try { setRelationships(await kernelGet<Relationship[]>(`/api/novels/${detail.id}/relationships`)) } catch (err) { setError(messageFrom(err)) }
  }
  useEffect(() => { void reloadRelationships() }, [detail.id])
  return <section className="space-y-5"><header className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">人物档案</p><h1 className="mt-1 text-lg font-semibold">人物关系</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">维护人物之间已经确认的关系、当前状态与变化章节；星图会基于这些关系展示全局关联。</p>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</header><RelationshipManager novelId={detail.id} relationships={relationships} characters={characters} onChanged={reloadRelationships} /></section>
}

function ForeshadowPanel({ detail }: { detail: NovelDetail }) {
  const [foreshadows, setForeshadows] = useState<Foreshadow[]>([])
  const [error, setError] = useState('')
  async function reloadForeshadows() {
    try {
      const [active, progressing, planned] = await Promise.all([
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows`),
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows?status=progressing`),
        kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows?status=planned`),
      ])
      setForeshadows([...active, ...progressing, ...planned])
    } catch (err) { setError(messageFrom(err)) }
  }
  useEffect(() => { void reloadForeshadows() }, [detail.id])
  async function update(id: string, action: 'ignore' | 'resolve') {
    try { await kernelPost(`/api/novels/${detail.id}/foreshadows/${id}/${action}`); await reloadForeshadows() } catch (err) { setError(messageFrom(err)) }
  }
  return <section className="space-y-5"><header className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">故事事实</p><h1 className="mt-1 text-lg font-semibold">伏笔与线索</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">这里记录当前有效、推进中和计划中的线索。人物关系请到“世界与人物 → 人物关系”维护。</p>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</header><section className="rounded-[18px] border border-border bg-workspace p-5"><div className="space-y-2">{foreshadows.map((item) => <article key={item.id} className="rounded-xl bg-active p-3 text-sm"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">{item.content || '暂无内容'}</p></div><span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">{item.status === 'progressing' ? '推进中' : item.status === 'planned' ? '计划中' : '进行中'}</span></div><div className="mt-3 flex gap-2"><button onClick={() => void update(item.id, 'ignore')} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-hover">忽略</button><button onClick={() => void update(item.id, 'resolve')} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-hover">解决</button></div></article>)}{foreshadows.length === 0 ? <p className="text-sm text-muted-foreground">暂无进行中的伏笔与线索。</p> : null}</div></section></section>
}

function RelationshipManager({ novelId, relationships, characters, onChanged }: { novelId: string; relationships: Relationship[]; characters: Character[]; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState<Relationship | null | 'new'>(null)
  const [form, setForm] = useState({ fromCharacterId: '', toCharacterId: '', relationType: '', sentiment: 'neutral', currentState: '', startedChapter: '0' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function open(item: Relationship | 'new') {
    setError(''); setEditing(item)
    setForm(item === 'new' ? { fromCharacterId: characters[0]?.id || '', toCharacterId: characters[1]?.id || '', relationType: '', sentiment: 'neutral', currentState: '', startedChapter: '0' } : { fromCharacterId: item.fromCharacterId || '', toCharacterId: item.toCharacterId || '', relationType: item.relationType || '', sentiment: item.sentiment || 'neutral', currentState: item.currentState || '', startedChapter: String(item.startedChapter || 0) })
  }
  async function save() {
    if (!form.fromCharacterId || !form.toCharacterId || form.fromCharacterId === form.toCharacterId) { setError('请选择两个不同人物'); return }
    setBusy(true); setError('')
    const body = { from_character_id: form.fromCharacterId, to_character_id: form.toCharacterId, relation_type: form.relationType.trim(), sentiment: form.sentiment, current_state: form.currentState.trim(), started_chapter: Math.max(0, Number(form.startedChapter) || 0), changed_chapter: Math.max(0, Number(form.startedChapter) || 0) }
    try { if (editing === 'new') await kernelPost(`/api/novels/${novelId}/relationships`, body); else if (editing) await kernelPatch(`/api/novels/${novelId}/relationships/${editing.id}`, body); setEditing(null); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function remove(item: Relationship) { if (!window.confirm(`确定删除 ${item.fromCharacterName || '人物'} 与 ${item.toCharacterName || '人物'} 的关系吗？`)) return; try { await kernelDelete(`/api/novels/${novelId}/relationships/${item.id}`); await onChanged() } catch (err) { setError(messageFrom(err)) } }
  return <><section className="rounded-[18px] border border-border bg-workspace p-5"><div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold">人物关系</h2><p className="mt-1 text-xs text-muted-foreground">手动补充或维护人物之间的关系；自动沉淀的关系会保留其正文来源。</p></div><button onClick={() => open('new')} disabled={characters.length < 2} className="rounded-lg border border-border px-3 py-2 text-xs hover:bg-hover disabled:opacity-50">新增关系</button></div>{error ? <p className="mt-3 text-xs text-destructive">{error}</p> : null}<div className="mt-4 space-y-2">{relationships.map((item) => <article key={item.id} className="rounded-xl bg-active p-3 text-sm"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{item.fromCharacterName || '人物'} × {item.toCharacterName || '人物'}</p><p className="mt-1 text-xs text-muted-foreground">{item.relationType || '关系待定义'} · {item.currentState || '暂无当前状态'}</p><p className="mt-1 text-[11px] text-muted-foreground">{item.sourceEventId ? '来自已采纳人物事实' : '手动维护'}{item.startedChapter ? ` · 自第 ${item.startedChapter} 章起` : ''}</p></div><div className="flex gap-1"><button onClick={() => open(item)} className="rounded px-2 py-1 text-xs hover:bg-surface">编辑</button><button onClick={() => void remove(item)} className="rounded px-2 py-1 text-xs text-destructive hover:bg-surface">删除</button></div></div></article>)}{relationships.length === 0 ? <p className="text-sm text-muted-foreground">暂无人物关系。可手动添加，或在采纳正文后由系统沉淀。</p> : null}</div></section>{editing ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"><div className="w-full max-w-lg rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"><div className="flex items-start justify-between"><div><h2 className="text-lg font-semibold">{editing === 'new' ? '新增人物关系' : '编辑人物关系'}</h2><p className="mt-1 text-sm text-muted-foreground">关系会进入故事事实，并在记忆星图中展示。</p></div><button onClick={() => setEditing(null)} className="rounded-lg p-1 hover:bg-hover"><X className="size-4" /></button></div><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium">人物 A<select value={form.fromCharacterId} onChange={(e) => setForm({ ...form, fromCharacterId: e.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2"><option value="">请选择</option>{characters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-sm font-medium">人物 B<select value={form.toCharacterId} onChange={(e) => setForm({ ...form, toCharacterId: e.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2"><option value="">请选择</option>{characters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-sm font-medium">关系类型<input value={form.relationType} onChange={(e) => setForm({ ...form, relationType: e.target.value })} placeholder="师徒、敌对、同伴…" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="text-sm font-medium">关系倾向<select value={form.sentiment} onChange={(e) => setForm({ ...form, sentiment: e.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2"><option value="positive">正面</option><option value="neutral">中性</option><option value="negative">负面</option><option value="complex">复杂</option></select></label></div><label className="mt-4 block text-sm font-medium">当前关系状态<textarea value={form.currentState} onChange={(e) => setForm({ ...form, currentState: e.target.value })} placeholder="例如：表面合作，彼此仍保持戒备。" className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3" /></label><label className="mt-4 block text-sm font-medium">从第几章开始<input value={form.startedChapter} onChange={(e) => setForm({ ...form, startedChapter: e.target.value })} inputMode="numeric" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}<div className="mt-6 flex justify-end gap-2"><button onClick={() => setEditing(null)} className="rounded-lg px-4 py-2 text-sm hover:bg-hover">取消</button><button disabled={busy} onClick={() => void save()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '保存中…' : '保存关系'}</button></div></div></div> : null}</>
}

function ChapterRevisionPanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const accepted = detail.chapters.filter((chapter) => chapter.status === 'accepted')
  const [chapterId, setChapterId] = useState(accepted.at(-1)?.id || '')
  const chapter = accepted.find((item) => item.id === chapterId) || accepted.at(-1)
  const [title, setTitle] = useState(chapter?.title || '')
  const [body, setBody] = useState(chapter?.body || '')
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => { setTitle(chapter?.title || ''); setBody(chapter?.body || ''); setNotice(''); setError('') }, [chapter?.id])
  if (!chapter) return <Unavailable title="暂无可修订章节" description="需要先采纳至少一章正文，才能进行人工或 AI 修订。" />
  const activeChapter = chapter
  async function reviseManually() {
    setBusy(true); setError(''); setNotice('')
    try { const result = await kernelPatch<{ affectedChapters?: number[] }>(`/api/novels/${detail.id}/chapters/${activeChapter.id}/revision`, { title, body }); setNotice(result.affectedChapters?.length ? `已采纳修订；后续 ${result.affectedChapters.length} 章等待一致性确认。` : '已采纳修订为正史。'); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function reviseWithAi() {
    if (instruction.trim().length < 3) { setError('请至少填写 3 个字符的修改建议'); return }
    setBusy(true); setError(''); setNotice('')
    try { await kernelPost(`/api/novels/${detail.id}/chapters/${activeChapter.id}/revision/ai`, { instruction, draft_body: body, focuses: [] }); setNotice('AI 修订已进入任务中心，完成后会生成替代草稿。'); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function auxiliary(path: string, payload?: unknown) {
    setBusy(true); setError(''); setNotice('')
    try { await kernelPost(path, payload); setNotice('任务已进入任务中心。'); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-lg font-semibold">章节修订</h1><p className="mt-1 text-sm text-muted-foreground">仅允许修订最近 10 章已采纳正文；修订会使相关人物记忆重新等待确认。</p></div><select value={chapter.id} onChange={(e) => setChapterId(e.target.value)} className="rounded-lg border bg-surface px-3 py-2 text-sm">{accepted.map((item) => <option key={item.id} value={item.id}>第{item.sequence}章 · {item.title}</option>)}</select></div><label className="mt-5 block text-sm font-medium">章节标题<input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">正文章节<textarea value={body} onChange={(e) => setBody(e.target.value)} className="mt-1.5 min-h-72 w-full rounded-xl border bg-surface p-3 text-sm leading-7 outline-none focus:ring-2 focus:ring-brand" /></label><div className="mt-4 flex flex-wrap gap-2"><button disabled={busy} onClick={() => void reviseManually()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">采纳为正文</button><button disabled={busy} onClick={() => void auxiliary(`/api/novels/${detail.id}/chapters/${chapter.id}/memory-reindex`)} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">重新索引本章记忆</button><button disabled={busy} onClick={() => void auxiliary(`/api/novels/${detail.id}/chapters/${chapter.id}/review`, { platform: detail.targetPlatform || '番茄' })} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">多视角审稿</button></div></div><div className="rounded-[18px] border border-border bg-workspace p-6"><h2 className="font-semibold">AI 生成替代草稿</h2><p className="mt-1 text-sm text-muted-foreground">使用当前草稿、前章和后续章节约束生成，结果在任务中心完成后可继续处理。</p><textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="告诉分身如何优化当前草稿，例如：强化主角的犹豫与后续伏笔衔接" className="mt-4 min-h-28 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /><button disabled={busy} onClick={() => void reviseWithAi()} className="mt-3 rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">{busy ? '处理中…' : '生成替代草稿'}</button>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}{notice ? <p className="mt-3 text-sm text-success">{notice}</p> : null}</div></section>
}

function AbilityPackPanel({ detail, onChanged, onOpenResults }: { detail: NovelDetail; onChanged: () => Promise<void>; onOpenResults: () => void }) {
  const accepted = detail.chapters.filter((chapter) => chapter.status === 'accepted')
  const [chapterId, setChapterId] = useState(accepted.at(-1)?.id || '')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const chapter = accepted.find((item) => item.id === chapterId) || accepted.at(-1)
  const review = ((chapter?.contextPack || {}).reviewTask || {}) as { status?: string; error?: string; verdict?: string }
  const reviewRunning = ['queued', 'running'].includes(review.status || '')
  useEffect(() => setChapterId((current) => accepted.some((item) => item.id === current) ? current : accepted.at(-1)?.id || ''), [detail.id, accepted.length])
  useEffect(() => {
    if (!reviewRunning) return
    const timer = window.setTimeout(() => { void onChanged() }, 2500)
    return () => window.clearTimeout(timer)
  }, [chapter?.id, review.status, onChanged])
  async function run(kind: 'review' | 'deslop') {
    if (!chapter) return
    setBusy(true); setError(''); setNotice('')
    try {
      if (kind === 'review') await kernelPost(`/api/novels/${detail.id}/chapters/${chapter.id}/review`, { platform: detail.targetPlatform || '番茄' })
      else await kernelPost(`/api/novels/${detail.id}/chapters/${chapter.id}/deslop`, { draft_body: '' })
      setNotice(`${kind === 'review' ? '多视角审稿' : '去 AI 味'}任务已进入后台任务。完成后可在“草稿与审校”查看结果。`)
      await onChanged()
    } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  if (!chapter) return <Unavailable title="能力包" description="需要先采纳至少一章正文，才能使用审稿与去 AI 味能力。" />
  return <section className="space-y-5"><header className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">写作工具</p><h1 className="mt-1 text-lg font-semibold">能力包</h1><p className="mt-1 text-sm text-muted-foreground">对已采纳正文执行独立工具。工具不会自动覆盖正文，结果统一进入“草稿与审校”。</p><select value={chapter.id} onChange={(event) => setChapterId(event.target.value)} className="mt-5 rounded-lg border bg-surface px-3 py-2 text-sm">{accepted.map((item) => <option key={item.id} value={item.id}>第{item.sequence}章 · {item.title}</option>)}</select></header><div className="grid gap-5 lg:grid-cols-2"><article className="rounded-[18px] border border-border bg-workspace p-6"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">多视角审稿</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">从结构与一致性、文字与角色两个维度审阅本章，输出问题分级清单，不会直接改写正文。</p></div>{review.status ? <span className="rounded-full bg-active px-2 py-1 text-xs">{review.status === 'succeeded' ? `已完成 · ${review.verdict || '有结果'}` : reviewRunning ? '进行中' : '失败'}</span> : null}</div><div className="mt-5 flex flex-wrap gap-2"><button disabled={busy || reviewRunning} onClick={() => void run('review')} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{reviewRunning ? '审稿进行中…' : busy ? '提交中…' : review.status === 'failed' ? '重新审稿' : '开始审稿'}</button>{review.status === 'succeeded' ? <button onClick={onOpenResults} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover">查看审稿结果</button> : null}</div>{reviewRunning ? <p className="mt-3 text-xs text-muted-foreground">任务完成前不能重复提交；页面会自动更新状态。</p> : null}{review.status === 'failed' ? <p className="mt-3 text-xs text-destructive">审稿失败：{review.error || '未返回失败原因'}。修复后可重新提交。</p> : null}</article><article className="rounded-[18px] border border-border bg-workspace p-6"><h2 className="font-semibold">去 AI 味</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">生成一份更自然的替代草稿，保留原正文。你可以对比后决定是否采纳。</p><button disabled={busy} onClick={() => void run('deslop')} className="mt-5 rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover disabled:opacity-50">{busy ? '提交中…' : '生成替代草稿'}</button></article></div>{notice ? <div className="rounded-xl border border-brand-border bg-brand-soft p-4 text-sm"><p>{notice}</p><button onClick={onOpenResults} className="mt-2 text-xs font-medium underline">查看草稿与审校</button></div> : null}{error ? <p className="rounded-xl border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : null}</section>
}

function MemoryEventsPanel({ detail, characters }: { detail: NovelDetail; characters: Character[] }) {
  const [characterId, setCharacterId] = useState(characters[0]?.id || '')
  const [events, setEvents] = useState<MemoryEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const character = characters.find((item) => item.id === characterId) || characters[0]
  useEffect(() => { setCharacterId((value) => characters.some((item) => item.id === value) ? value : characters[0]?.id || '') }, [characters])
  async function reload() { if (!character) return; setLoading(true); setError(''); try { setEvents(await kernelGet<MemoryEvent[]>(`/api/novels/${detail.id}/characters/${character.id}/memory-events`)) } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) } }
  useEffect(() => { void reload() }, [character?.id])
  async function decide(event: MemoryEvent, action: 'accept' | 'ignore') { if (!character) return; try { await kernelPost(`/api/novels/${detail.id}/characters/${character.id}/memory-events/${event.id}/decision?action=${action}`); await reload() } catch (err) { setError(messageFrom(err)) } }
  if (!character) return <Unavailable title="暂无人物记忆" description="导入分析和人物建模完成后，会在这里展示每条记忆的原文证据与审阅状态。" />
  return <section className="rounded-[18px] border border-border bg-workspace"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5"><div><h1 className="font-semibold">人物档案</h1><p className="mt-1 text-xs text-muted-foreground">档案中的每条关键事实都能回溯到原文证据；可靠事实会用于后续写作和人物对话。</p></div><div className="flex items-center gap-2"><select value={character.id} onChange={(e) => setCharacterId(e.target.value)} className="rounded-lg border bg-surface px-3 py-2 text-sm">{characters.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button onClick={() => void reload()} className="rounded-lg p-2 hover:bg-hover"><RefreshCw className="size-4" /></button></div></header><div className="space-y-4 p-5"><article className="rounded-xl bg-active p-4"><p className="text-xs text-muted-foreground">{character.role || '人物'} · {displayStatus(character.importance, displayStatus(character.modelingStatus, '已建立档案'))}</p><h2 className="mt-1 text-lg font-semibold">{character.name}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{character.currentState || character.identity || '当前状态仍待从正文继续沉淀。'}</p>{character.aliases?.length ? <p className="mt-2 text-xs text-muted-foreground">别名：{character.aliases.join('、')}</p> : null}</article><div><h2 className="text-sm font-semibold">人物事实与原文证据</h2><p className="mt-1 text-xs text-muted-foreground">以下内容属于人物档案的一部分，不再单独维护入口。</p></div>{loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />正在读取人物事实</p> : null}{error ? <p className="text-sm text-destructive">{error}</p> : null}{!loading ? events.map((event) => <article key={event.id} className="rounded-xl border border-border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><span className="rounded-full bg-active px-2 py-1 text-xs">{displayMemoryEventType(event.eventType)}</span><p className="mt-2 font-medium">{event.value}</p><p className="mt-2 text-xs text-muted-foreground">物理段 {event.validFromSourceSegment || 0} · {displayStatus(event.knowledgeScope, '客观正史')} · {displayStatus(event.evidenceStatus, '待核实')}</p></div><span className={`rounded-full px-2 py-1 text-xs ${event.reviewStatus === 'accepted' ? 'bg-brand-soft' : event.reviewStatus === 'ignored' ? 'bg-active text-muted-foreground' : 'bg-warning/15 text-warning'}`}>{displayStatus(event.reviewStatus, '待处理')}</span></div>{event.quote ? <blockquote className="mt-3 border-l-2 border-brand-border pl-3 text-sm leading-6 text-muted-foreground">“{event.quote}”</blockquote> : null}{event.reviewReason ? <p className="mt-2 text-xs text-warning">{event.reviewReason}</p> : null}{event.conflicts?.length ? <p className="mt-2 text-xs text-destructive">存在 {event.conflicts.length} 条同类时间冲突。</p> : null}{event.reviewStatus === 'pending' ? <div className="mt-3 flex gap-2"><button onClick={() => void decide(event, 'accept')} className="rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-primary-foreground">采纳</button><button onClick={() => void decide(event, 'ignore')} className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-hover">忽略</button></div> : null}</article>) : null}{!loading && events.length === 0 ? <p className="text-sm text-muted-foreground">该人物暂无已抽取的人物事实。</p> : null}</div></section>
}

function CandidatePanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  async function reload(keyword = query) {
    setLoading(true); setError('')
    try {
      const data = await kernelGet<{ localCandidates?: Candidate[] }>(`/api/novels/${detail.id}/memory-index-candidates?keyword=${encodeURIComponent(keyword)}&page=1&page_size=50`)
      setCandidates(data.localCandidates || [])
    } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) }
  }
  useEffect(() => { void reload('') }, [detail.id])
  async function accept(candidate: Candidate, model = false) {
    setError('')
    try {
      if (model) {
        await kernelPost(`/api/novels/${detail.id}/memory-index-candidates/${candidate.id}/model`)
      } else {
        const name = candidate.canonicalName || candidate.name
        await kernelPost(`/api/novels/${detail.id}/memory-index-candidates/accept?name=${encodeURIComponent(name)}&candidate_id=${encodeURIComponent(candidate.id)}`)
      }
      await reload(); await onChanged()
    } catch (err) { setError(messageFrom(err)) }
  }
  return <section className="rounded-[18px] border border-border bg-workspace"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5"><div><h1 className="font-semibold">候选人物</h1><p className="mt-1 text-xs text-muted-foreground">候选由导入分析生成；清洗结论与出现证据均可见。</p></div><form onSubmit={(e) => { e.preventDefault(); void reload() }} className="flex gap-2"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索名字" className="w-36 rounded-lg border bg-surface px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand" /><button className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-hover">搜索</button></form></header><div className="space-y-3 p-5">{loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />正在读取候选人物</p> : null}{error ? <p className="text-sm text-destructive">{error}</p> : null}{!loading ? candidates.map((item) => <article key={item.id} className="rounded-xl border border-border p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-medium">{item.name}{item.canonicalName && item.canonicalName !== item.name ? <span className="ml-2 text-sm font-normal text-muted-foreground">→ {item.canonicalName}</span> : null}</p><p className="mt-1 text-xs text-muted-foreground">出现 {item.mentionSegmentCount || 0} 个物理段 · {item.cleaningAction || '待处理'}</p>{item.cleaningReason ? <p className="mt-2 text-xs text-muted-foreground">{item.cleaningReason}</p> : null}</div><div className="flex gap-2"><button onClick={() => void accept(item)} className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-hover">采纳人物</button><button onClick={() => void accept(item, true)} className="rounded-md bg-foreground px-3 py-1.5 text-xs text-primary-foreground">采纳并建模</button></div></div>{item.evidenceSnippets?.length ? <p className="mt-3 rounded-lg bg-active p-2 text-xs leading-5 text-muted-foreground">{item.evidenceSnippets[0]}</p> : null}</article>) : null}{!loading && candidates.length === 0 ? <p className="text-sm text-muted-foreground">没有待确认候选人物。</p> : null}</div></section>
}

function ChapterResultPanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const reviewable = detail.chapters.filter((chapter) => chapter.status === 'accepted' || chapter.status === 'ready_for_author').sort((left, right) => right.sequence - left.sequence)
  const [chapterId, setChapterId] = useState(reviewable[0]?.id || '')
  const [snapshots, setSnapshots] = useState<RevisionSnapshot[]>([])
  const [snapshotId, setSnapshotId] = useState('')
  const [editingDraft, setEditingDraft] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftBody, setDraftBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const chapter = reviewable.find((item) => item.id === chapterId) || reviewable[0]
  const pack = (chapter?.contextPack || {}) as Record<string, unknown>
  const revision = (pack.revisionTask || {}) as GeneratedDraft
  const review = (pack.reviewTask || {}) as { status?: string; verdict?: string; structureSummary?: string; proseSummary?: string; findings?: Array<{ severity?: string; category?: string; title?: string; description?: string; evidence?: string }> ; error?: string }
  useEffect(() => { setChapterId((current) => reviewable.some((item) => item.id === current) ? current : reviewable[0]?.id || '') }, [detail.id, reviewable.length])
  useEffect(() => { setSnapshotId(''); setEditingDraft(false); setDraftTitle(chapter?.title || ''); setDraftBody(chapter?.body || ''); if (!chapter || chapter.status !== 'ready_for_author') { setSnapshots([]); return } void kernelGet<RevisionSnapshot[]>(`/api/novels/${detail.id}/chapters/${chapter.id}/revisions`).then(setSnapshots).catch((err) => setError(messageFrom(err))) }, [detail.id, chapter?.id, chapter?.status])
  async function acceptDraft(draft: GeneratedDraft) {
    if (!chapter || !draft.body || !window.confirm('将此草稿采纳为正文正史？当前正文会进入修订历史。')) return
    setBusy(true); setError('')
    try { await kernelPatch(`/api/novels/${detail.id}/chapters/${chapter.id}/revision`, { title: draft.title || chapter.title, body: draft.body }); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function acceptGeneratedChapter() { if (!chapter || chapter.status !== 'ready_for_author' || !window.confirm('将此章节细纲生成的草稿采纳为正文正史？')) return; setBusy(true); setError(''); try { await kernelPost(`/api/novels/${detail.id}/chapters/${chapter.id}/accept`); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function restoreSnapshot(snapshot: RevisionSnapshot) { if (!chapter || chapter.status !== 'ready_for_author' || !window.confirm(`恢复“${snapshot.title}”草稿版本？当前草稿会保留为新的历史版本。`)) return; setBusy(true); setError(''); try { await kernelPatch(`/api/novels/${detail.id}/chapters/${chapter.id}/draft`, { title: snapshot.title, body: snapshot.body }); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function saveDraft() { if (!chapter || !draftBody.trim()) return; setBusy(true); setError(''); try { await kernelPatch(`/api/novels/${detail.id}/chapters/${chapter.id}/draft`, { title: draftTitle, body: draftBody }); setEditingDraft(false); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function clearReview() {
    if (!chapter) return
    setBusy(true); setError('')
    try { await kernelDelete(`/api/novels/${detail.id}/chapters/${chapter.id}/review`); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  if (!chapter) return <Unavailable title="暂无草稿与审校内容" description="请先从章节细纲生成草稿，或采纳至少一章正文后使用能力包审校。" />
  const selectedSnapshot = snapshots.find((item) => item.id === snapshotId)
  return <section className="space-y-5"><header className="rounded-[18px] border border-border bg-workspace p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="font-semibold">草稿与审校</h1><p className="mt-1 text-xs text-muted-foreground">全书同时只保留一份未采纳草稿；修订历史只记录该草稿的编辑过程。</p></div><select value={chapter.id} onChange={(event) => setChapterId(event.target.value)} className="rounded-lg border bg-surface px-3 py-2 text-sm">{reviewable.map((item) => <option key={item.id} value={item.id}>第{item.sequence}章 · {item.title} · {chapterStatusLabel(item.status)}</option>)}</select></div><div className="mt-4"><label className="text-xs text-muted-foreground">本草稿编辑历史<select disabled={chapter.status !== 'ready_for_author'} value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)} className="ml-2 rounded-lg border bg-surface px-3 py-2 text-sm disabled:opacity-50"><option value="">{chapter.status === 'ready_for_author' ? `选择历史版本（${snapshots.length}）` : '仅未采纳草稿保留编辑历史'}</option>{snapshots.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.wordCount || 0} 字</option>)}</select></label></div>{selectedSnapshot ? <article className="mt-4 rounded-xl bg-active p-4"><p className="font-medium">{selectedSnapshot.title}</p><p className="mt-3 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{selectedSnapshot.body}</p><button disabled={busy} onClick={() => void restoreSnapshot(selectedSnapshot)} className="mt-3 rounded-lg border border-border px-3 py-2 text-xs hover:bg-hover">恢复此草稿版本</button></article> : null}</header>{error ? <p className="rounded-xl border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}<section className="rounded-[18px] border border-border bg-workspace p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">多视角审稿</h2><p className="mt-1 text-xs text-muted-foreground">状态：{review.status ? displayTaskStatus(review.status) : '暂无审稿任务'} {review.verdict ? `· ${displayReviewVerdict(review.verdict)}` : ''}</p></div><div className="flex gap-2">{chapter.status === 'ready_for_author' ? <button disabled={busy || !chapter.body} onClick={() => void acceptGeneratedChapter()} className="rounded-lg bg-foreground px-3 py-2 text-xs text-primary-foreground disabled:opacity-50">采纳为正文</button> : null}{review.status === 'succeeded' ? <button disabled={busy} onClick={() => void clearReview()} className="rounded-lg border border-border px-3 py-2 text-xs hover:bg-hover">清除结果</button> : null}</div></div>{review.structureSummary ? <p className="mt-4 rounded-xl bg-active p-3 text-sm leading-6">结构：{review.structureSummary}</p> : null}{review.proseSummary ? <p className="mt-3 rounded-xl bg-active p-3 text-sm leading-6">文字与角色：{review.proseSummary}</p> : null}</section>{chapter.status === 'ready_for_author' ? <section className="rounded-[18px] border border-brand-border bg-brand-soft p-5"><div className="flex justify-between gap-3"><div><p className="text-xs font-medium text-brand">章节细纲生成的草稿</p><h2 className="mt-1 font-semibold">第{chapter.sequence}章 · {chapter.title}</h2></div><button onClick={() => setEditingDraft((value) => !value)} className="rounded-lg border border-brand-border px-3 py-2 text-xs hover:bg-surface">{editingDraft ? '取消编辑' : '编辑草稿'}</button></div>{editingDraft ? <><input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} className="mt-4 w-full rounded-lg border bg-surface px-3 py-2 text-sm" /><textarea value={draftBody} onChange={(event) => setDraftBody(event.target.value)} className="mt-3 min-h-80 w-full rounded-xl border bg-surface p-3 text-sm leading-7" /><button disabled={busy} onClick={() => void saveDraft()} className="mt-3 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">确认编辑并保存历史</button></> : <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-body-foreground">{chapter.body || '草稿正文尚未生成完成。'}</p>}</section> : null}</section>
}

function MemoryGraphPanel({ detail, characters, focusIds, onFocusIdsChange }: { detail: NovelDetail; characters: Character[]; focusIds: string[]; onFocusIdsChange: (ids: string[]) => void }) {
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [events, setEvents] = useState<MemoryEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [pan, setPan] = useState<{ x: number; y: number } | null>(null)
  const selected = characters.find((item) => item.id === selectedId)
  const nodes = characters.map((character, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(characters.length, 1)
    const radiusX = characters.length < 4 ? 190 : 245
    const radiusY = characters.length < 4 ? 150 : 190
    return { ...character, x: 500 + Math.cos(angle) * radiusX, y: 300 + Math.sin(angle) * radiusY }
  })
  const nodeMap = new Map(nodes.map((item) => [item.id, item]))
  const links = relationships.map((item) => ({ ...item, from: nodeMap.get(item.fromCharacterId || ''), to: nodeMap.get(item.toCharacterId || '') })).filter((item) => item.from && item.to)
  async function reloadGraph() {
    setLoading(true); setError('')
    try { setRelationships(await kernelGet<Relationship[]>(`/api/novels/${detail.id}/relationships`)) } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) }
  }
  useEffect(() => { void reloadGraph() }, [detail.id])
  useEffect(() => {
    if (!selected) { setEvents([]); return }
    void kernelGet<MemoryEvent[]>(`/api/novels/${detail.id}/characters/${selected.id}/memory-events`).then((result) => setEvents(result.filter((item) => item.reviewStatus === 'accepted' && item.evidenceStatus !== 'rejected'))).catch((err) => setError(messageFrom(err)))
  }, [detail.id, selected?.id])
  function onWheel(event: WheelEvent<SVGSVGElement>) { event.preventDefault(); setZoom((value) => Math.max(0.62, Math.min(1.7, value + (event.deltaY < 0 ? 0.1 : -0.1)))) }
  function onPointerDown(event: ReactPointerEvent<SVGSVGElement>) { if ((event.target as Element).closest('[data-memory-node]')) return; setPan({ x: event.clientX, y: event.clientY }); event.currentTarget.setPointerCapture(event.pointerId) }
  function onPointerMove(event: ReactPointerEvent<SVGSVGElement>) { if (!pan) return; setOffset((value) => ({ x: value.x + (event.clientX - pan.x) * 1.35, y: value.y + (event.clientY - pan.y) * 1.35 })); setPan({ x: event.clientX, y: event.clientY }) }
  function toggleFocus(id: string) { onFocusIdsChange(focusIds.includes(id) ? focusIds.filter((item) => item !== id) : [...focusIds, id]) }
  const facts = events.slice().sort((a, b) => (a.validFromSourceSegment || 0) - (b.validFromSourceSegment || 0))
  return <section className="rounded-[18px] border border-border bg-workspace p-5"><header className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="font-semibold">人物记忆星图</h1><p className="mt-1 text-xs text-muted-foreground">全景仅呈现人物与关系；点击人物查看已采纳的正史事实。</p></div><button onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }); setSelectedId('') }} className="rounded-lg border border-border px-3 py-2 text-xs hover:bg-hover">重置星图</button></header>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}{loading ? <p className="flex min-h-96 items-center justify-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />正在读取人物关系</p> : null}{!loading && nodes.length === 0 ? <p className="flex min-h-96 items-center justify-center text-sm text-muted-foreground">先建立人物档案，星图才会点亮。</p> : null}{!loading && nodes.length ? <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]"><div className="relative min-h-[520px] overflow-hidden rounded-[16px] border border-border bg-[radial-gradient(circle_at_50%_45%,#f8fbf5_0,#edf3eb_58%,#e4ece2_100%)]"><svg viewBox="0 0 1000 600" className="h-[520px] w-full touch-none" role="img" aria-label="人物关系记忆星图" onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => setPan(null)} onPointerLeave={() => setPan(null)}><g transform={`translate(${offset.x} ${offset.y}) scale(${zoom})`}><g>{links.map((link) => <g key={link.id}><line x1={link.from!.x} y1={link.from!.y} x2={link.to!.x} y2={link.to!.y} stroke="#7e9bbb" strokeWidth="2.5" /><text x={(link.from!.x + link.to!.x) / 2} y={(link.from!.y + link.to!.y) / 2 - 8} textAnchor="middle" fill="#55718e" fontSize="12">{link.relationType || '关联'}</text></g>)}</g>{nodes.map((item) => <g key={item.id} data-memory-node="true" transform={`translate(${item.x} ${item.y})`} onClick={() => setSelectedId(item.id)} className="cursor-pointer"><circle r="34" fill={focusIds.includes(item.id) ? '#04c853' : '#527faf'} stroke={selectedId === item.id ? '#f2c95d' : '#ffffff'} strokeWidth={selectedId === item.id ? 4 : 2} /><text y="5" textAnchor="middle" fill="#fff" fontSize="12" fontWeight="700">{item.name.slice(0, 3)}</text><text y="56" textAnchor="middle" fill="#4e5f50" fontSize="13">{item.name}</text></g>)}</g></svg></div><aside className="min-h-[520px] rounded-[16px] border border-border bg-surface p-4">{selected ? <><p className="text-xs text-muted-foreground">{selected.role || '人物'} · {displayStatus(selected.status, '活跃')}</p><h2 className="mt-1 text-lg font-semibold">{selected.name}</h2><p className="mt-3 rounded-xl bg-active p-3 text-sm leading-6">{selected.currentState || selected.identity || '暂无当前状态'}</p><button onClick={() => toggleFocus(selected.id)} className="mt-3 w-full rounded-lg border border-border px-3 py-2 text-sm hover:bg-hover">{focusIds.includes(selected.id) ? '移出下一章上下文' : '纳入下一章上下文'}</button><div className="mt-5"><p className="text-xs font-medium text-muted-foreground">已采纳正史事实 · {facts.length}</p><div className="mt-2 max-h-72 space-y-2 overflow-auto">{facts.map((event) => <article key={event.id} className="rounded-lg bg-active p-2.5"><p className="text-xs font-medium">{displayMemoryEventType(event.eventType)} · 物理段 {event.validFromSourceSegment || 0}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{event.value}</p></article>)}{facts.length === 0 ? <p className="text-xs leading-5 text-muted-foreground">暂无已采纳人物记忆。</p> : null}</div></div></> : <div className="flex h-full items-center justify-center text-center text-sm leading-6 text-muted-foreground">从星图选择人物，查看其当前状态与正史事实。</div>}</aside></div> : null}</section>
}

function BookSetupPanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const [targetWords, setTargetWords] = useState(String(detail.targetWords || 0))
  const [corePromise, setCorePromise] = useState(detail.corePromise || '')
  const [agency, setAgency] = useState(detail.protagonistAgency || '')
  const [audience, setAudience] = useState(detail.bookSetup?.targetAudience || '')
  const [logline, setLogline] = useState(detail.bookSetup?.logline || '')
  const [conflict, setConflict] = useState(detail.bookSetup?.coreConflict || '')
  const [positioning, setPositioning] = useState(detail.bookSetup?.genrePositioning || '')
  const [contribution, setContribution] = useState(detail.bookSetup?.irreplaceableContribution || '')
  const [settlement, setSettlement] = useState(detail.bookSetup?.expectedSettlement || '')
  const [assetBoundary, setAssetBoundary] = useState(detail.bookSetup?.coreAssetsBoundary || '')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    setTargetWords(String(detail.targetWords || 0)); setCorePromise(detail.corePromise || ''); setAgency(detail.protagonistAgency || ''); setAudience(detail.bookSetup?.targetAudience || ''); setLogline(detail.bookSetup?.logline || ''); setConflict(detail.bookSetup?.coreConflict || ''); setPositioning(detail.bookSetup?.genrePositioning || ''); setContribution(detail.bookSetup?.irreplaceableContribution || ''); setSettlement(detail.bookSetup?.expectedSettlement || ''); setAssetBoundary(detail.bookSetup?.coreAssetsBoundary || '')
  }, [detail.id, detail.targetWords, detail.corePromise, detail.protagonistAgency, detail.bookSetup])
  async function save() {
    const words = Number(targetWords)
    if (!Number.isInteger(words) || words < 0) { setError('目标字数需为不小于 0 的整数'); return }
    if (!corePromise.trim() || !agency.trim()) { setError('请补全本书方向和主角推动方式'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      await kernelPatch(`/api/novels/${detail.id}/book-setup`, { target_words: words, core_promise: corePromise.trim(), protagonist_agency: agency.trim(), target_audience: audience.trim(), logline: logline.trim(), core_conflict: conflict.trim(), genre_positioning: positioning.trim(), irreplaceable_contribution: contribution.trim(), expected_settlement: settlement.trim(), core_assets_boundary: assetBoundary.trim() })
      setNotice('本书方向已保存。未采纳草稿可能需要按最新方向重新生成。'); await onChanged()
    } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  if (detail.sourceMode === 'script') return <Unavailable title="本书方向" description="剧本以已导入正文为准，不在这里修改创作方向。" />
  return <section className="space-y-5">
    <div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">创作基础</p><h1 className="mt-1 text-lg font-semibold">本书方向</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">用日常语言确定这本书为什么值得追。系统会把这些信息转成长期写作约束，不需要理解任何创作术语。</p><div className="mt-5 grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">预计总字数<input value={targetWords} onChange={(event) => setTargetWords(event.target.value)} inputMode="numeric" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label><label className="block text-sm font-medium">题材定位<input value={positioning} onChange={(event) => setPositioning(event.target.value)} placeholder="例如：热血升级流、都市悬疑" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label></div><label className="mt-4 block text-sm font-medium">目标读者<textarea value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="例如：喜欢成长逆袭、强冲突和持续爽点的读者。" className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label></div>
    <div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">吸引读者的主线</p><label className="mt-3 block text-sm font-medium">一句话梗概<p className="mt-1 text-xs font-normal text-muted-foreground">谁，在什么困境下，为了什么目标，必须面对什么阻碍。</p><textarea value={logline} onChange={(event) => setLogline(event.target.value)} placeholder="例如：被逐出家门的少年，为夺回失去的一切，必须在强敌环伺的宗门试炼中证明自己。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-5 block text-sm font-medium">读者会为什么追下去？<textarea value={corePromise} onChange={(event) => setCorePromise(event.target.value)} placeholder="持续提供的爽点、情绪或核心期待。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-5 block text-sm font-medium">核心冲突<textarea value={conflict} onChange={(event) => setConflict(event.target.value)} placeholder="主角目标与最主要阻力之间，长期无法回避的矛盾。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label></div>
    <div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">主角在关键情节中的位置</p><p className="mt-1 text-sm leading-6 text-muted-foreground">写清关键局面为什么需要主角，以及主角付出后应该得到什么。队友可以帮忙，但不应无铺垫地替主角完成核心转折。</p><label className="mt-4 block text-sm font-medium">主角有什么别人不能替代的优势？<textarea value={contribution} onChange={(event) => setContribution(event.target.value)} placeholder="例如：能辨认失传符文；掌握独家线索；能在关键时刻作出其他人不敢作的判断。" className="mt-1.5 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-5 block text-sm font-medium">遇到关键问题时，主角会怎样行动并带来转折？<textarea value={agency} onChange={(event) => setAgency(event.target.value)} placeholder="例如：主动调查、承担风险、布局后让同伴执行；不会只等别人来拯救。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-5 block text-sm font-medium">主角付出后，应获得什么回报？<textarea value={settlement} onChange={(event) => setSettlement(event.target.value)} placeholder="例如：关键资源、身份认可、选择权，或与目标人物的关系推进。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-5 block text-sm font-medium">哪些重要能力、资源或秘密不能轻易失去？<textarea value={assetBoundary} onChange={(event) => setAssetBoundary(event.target.value)} placeholder="例如：独家能力不能无条件交给机构；若合作，主角需要换到保护、权限或更大的主动权。" className="mt-2 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><div className="mt-5 flex items-center gap-3"><button disabled={busy} onClick={() => void save()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '保存中…' : '保存本书方向'}</button>{notice ? <p className="text-sm text-success">{notice}</p> : null}{error ? <p className="text-sm text-destructive">{error}</p> : null}</div></div>
  </section>
}

function WorkbenchSidebar({ groups, section, onSelect }: { groups: WorkbenchGroup[]; section: string; onSelect: (section: string) => void }) {
  return <aside className="min-h-0 overflow-auto border-r border-border bg-workspace p-3"><nav className="space-y-1" aria-label="工作台导航">{groups.map((group) => {
    const Icon = group.icon
    const active = section === group.target || Boolean(group.children?.some((item) => item.id === section))
    return <div key={group.id} className="pt-1"><button onClick={() => onSelect(group.target)} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm ${active ? 'bg-active font-medium' : 'text-muted-foreground hover:bg-hover hover:text-foreground'}`}><Icon className="size-4" />{group.label}{group.unavailable ? <span className="ml-auto text-[10px] text-muted-foreground">未开放</span> : null}</button>{active && group.children?.length ? <div className="ml-5 mt-1 space-y-0.5 border-l border-border pl-2">{group.children.map((item) => <button key={item.id} onClick={() => onSelect(item.id)} className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs ${section === item.id ? 'bg-brand-soft font-medium text-foreground' : 'text-muted-foreground hover:bg-hover hover:text-foreground'}`}><span>{item.label}</span>{item.unavailable ? <span className="text-[10px] text-muted-foreground">未开放</span> : null}</button>)}</div> : null}</div>
  })}</nav></aside>
}

function OutlinePanel({ detail, onChanged, onRequestSuggestion }: { detail: NovelDetail; onChanged: () => Promise<void>; onRequestSuggestion: () => void }) {
  const units = detail.plotUnits || []
  const [selectedId, setSelectedId] = useState('')
  const [unit, setUnit] = useState<Partial<PlotUnit>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const selected = units.find((item) => item.id === selectedId) || units.find((item) => item.status === 'active') || units[0]
  useEffect(() => { const current = selected || { title: '', promise: '', protagonistGoal: '', obstacle: '', payoff: '', forbiddenReveals: '', status: 'planned' as const }; setSelectedId(selected?.id || ''); setUnit(current) }, [detail.id, detail.plotUnits])
  function startNew() { setSelectedId(''); setUnit({ title: '', promise: '', protagonistGoal: '', obstacle: '', payoff: '', forbiddenReveals: '', status: 'planned' }); setNotice(''); setError('') }
  function select(id: string) { const next = units.find((item) => item.id === id); if (next) { setSelectedId(id); setUnit(next); setNotice(''); setError('') } }
  async function save() {
    if (!unit.title?.trim()) { setError('请填写剧情单元名称'); return }
    setBusy(true); setError(''); setNotice('')
    const body = { title: unit.title.trim(), promise: unit.promise || '', protagonist_goal: unit.protagonistGoal || '', obstacle: unit.obstacle || '', payoff: unit.payoff || '', forbidden_reveals: unit.forbiddenReveals || '', status: unit.status || 'planned' }
    try { if (selectedId) await kernelPatch(`/api/novels/${detail.id}/plot-units/${selectedId}`, body); else await kernelPost(`/api/novels/${detail.id}/plot-units`, body); setNotice('剧情单元已保存。标记为“当前进行”后，下一章会使用它。'); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  async function remove() { if (!selectedId || !window.confirm('确定删除这个尚未写入章节的剧情单元吗？')) return; try { await kernelDelete(`/api/novels/${detail.id}/plot-units/${selectedId}`); startNew(); await onChanged() } catch (err) { setError(messageFrom(err)) } }
  if (detail.sourceMode === 'script') return <Unavailable title="后续剧情" description="剧本以已导入正文为准，不在此修改后续剧情安排。" />
  return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">分段规划</p><h1 className="mt-1 text-lg font-semibold">剧情单元</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">把故事拆成连续的几段。只有一个单元处于“当前进行”，写下一章会按它来承接。</p><div className="mt-4 flex flex-wrap gap-2">{units.map((item) => <button key={item.id} onClick={() => select(item.id)} className={`rounded-lg border px-3 py-2 text-sm ${selectedId === item.id ? 'border-brand bg-brand-soft' : 'border-border hover:bg-hover'}`}>第{item.sequence}段 · {item.title}{item.status === 'active' ? ' · 当前' : ''}</button>)}<button onClick={onRequestSuggestion} className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-foreground shadow-sm hover:opacity-90">剧情单元建议生成</button></div></div><div className="rounded-[18px] border border-border bg-workspace p-6"><div className="grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">这一段剧情叫什么？<input value={unit.title || ''} onChange={(event) => setUnit({ ...unit, title: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label><label className="block text-sm font-medium">使用状态<select value={unit.status || 'planned'} onChange={(event) => setUnit({ ...unit, status: event.target.value as PlotUnit['status'] })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2"><option value="planned">后续规划</option><option value="active">当前进行</option><option value="completed">已完成</option><option value="archived">归档</option></select></label></div><label className="mt-4 block text-sm font-medium">这一段先让读者期待什么？<p className="mt-1 text-xs font-normal text-muted-foreground">写下这一段会逐步回应的谜题、反击、升级或关系进展；完成后可保留记录，下一段再建立新的期待。</p><textarea value={unit.promise || ''} onChange={(event) => setUnit({ ...unit, promise: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">主角这一段想做到什么？<textarea value={unit.protagonistGoal || ''} onChange={(event) => setUnit({ ...unit, protagonistGoal: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">主要阻碍<textarea value={unit.obstacle || ''} onChange={(event) => setUnit({ ...unit, obstacle: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">这一段结束时要给读者什么回报？<textarea value={unit.payoff || ''} onChange={(event) => setUnit({ ...unit, payoff: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">暂时不要揭开的内容<textarea value={unit.forbiddenReveals || ''} onChange={(event) => setUnit({ ...unit, forbiddenReveals: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><div className="mt-5 flex flex-wrap gap-3"><button disabled={busy} onClick={() => void save()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '保存中…' : selectedId ? '保存剧情单元' : '创建剧情单元'}</button>{selectedId ? <button disabled={busy} onClick={() => void remove()} className="rounded-lg px-4 py-2 text-sm text-destructive hover:bg-hover">删除</button> : null}{notice ? <p className="self-center text-sm text-success">{notice}</p> : null}{error ? <p className="self-center text-sm text-destructive">{error}</p> : null}</div></div></section>
}

const defaultFullOutlineStages = (): FullOutlineStage[] => [
  { title: '开篇期', chapterRange: '', goal: '', turningPoint: '', forbiddenReveals: '' },
  { title: '发展期', chapterRange: '', goal: '', turningPoint: '', forbiddenReveals: '' },
  { title: '高潮期', chapterRange: '', goal: '', turningPoint: '', forbiddenReveals: '' },
  { title: '收尾期', chapterRange: '', goal: '', turningPoint: '', forbiddenReveals: '' },
]

function fullOutlineFromDetail(detail: NovelDetail): { overview: string; ending: string; emotionalCurve: string; keyHooks: string; endgameReserves: string; progressionLadders: string; stages: FullOutlineStage[] } {
  const source = detail.fullOutline || {}
  const stages = (source.stages || []).map((stage) => ({ title: stage.title || '', chapterRange: stage.chapterRange || '', goal: stage.goal || '', turningPoint: stage.turningPoint || '', forbiddenReveals: stage.forbiddenReveals || '' }))
  return { overview: source.overview || '', ending: source.ending || '', emotionalCurve: source.emotionalCurve || '', keyHooks: source.keyHooks || '', endgameReserves: source.endgameReserves || '', progressionLadders: source.progressionLadders || '', stages: stages.length ? stages : defaultFullOutlineStages() }
}

function FullOutlinePanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const [outline, setOutline] = useState(() => fullOutlineFromDetail(detail))
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  useEffect(() => setOutline(fullOutlineFromDetail(detail)), [detail.id, detail.fullOutline])
  function updateStage(index: number, field: keyof FullOutlineStage, value: string) { setOutline((current) => ({ ...current, stages: current.stages.map((stage, stageIndex) => stageIndex === index ? { ...stage, [field]: value } : stage) })) }
  async function save() {
    const stages = outline.stages.filter((stage) => stage.title.trim())
    if (!outline.overview.trim()) { setError('请先写清全书主线概览'); return }
    if (stages.length !== outline.stages.length) { setError('每个保留的阶段都需要名称；空白阶段请移除'); return }
    setBusy(true); setNotice(''); setError('')
    try {
      await kernelPatch(`/api/novels/${detail.id}/full-outline`, {
        overview: outline.overview,
        ending: outline.ending,
        emotional_curve: outline.emotionalCurve,
        key_hooks: outline.keyHooks,
        endgame_reserves: outline.endgameReserves,
        progression_ladders: outline.progressionLadders,
        stages: stages.map((stage) => ({ title: stage.title, chapter_range: stage.chapterRange, goal: stage.goal, turning_point: stage.turningPoint, forbidden_reveals: stage.forbiddenReveals })),
      })
      setNotice('全书大纲已保存，后续新草稿会按它约束长期方向。')
      await onChanged()
    } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">长期规划</p><h1 className="mt-1 text-lg font-semibold">全书大纲</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">先确定整本书会如何展开、在哪里转折、哪些信息暂时不能揭开。它约束长期方向，不替代当前剧情单元和章节细纲。</p><label className="mt-5 block text-sm font-medium">全书主线概览<textarea value={outline.overview} onChange={(event) => setOutline({ ...outline, overview: event.target.value })} placeholder="主角从什么处境出发，经历什么主线冲突，最终完成怎样的改变或目标。" className="mt-1.5 min-h-32 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">终局方向<textarea value={outline.ending} onChange={(event) => setOutline({ ...outline, ending: event.target.value })} placeholder="最终要解决的核心矛盾、关系落点或结局余韵；可以先写暂定方案。" className="mt-1.5 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><div className="mt-4 grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">终局前暂时不能揭开的事<textarea value={outline.endgameReserves} onChange={(event) => setOutline({ ...outline, endgameReserves: event.target.value })} placeholder="例如：终极敌人的真实身份、金手指的上限、主角最终身世；注明大概在哪个阶段才可揭开。" className="mt-1.5 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="block text-sm font-medium">主角会跨过哪些成长台阶？<textarea value={outline.progressionLadders} onChange={(event) => setOutline({ ...outline, progressionLadders: event.target.value })} placeholder="例如：外门试炼 → 宗门核心 → 地域争霸 → 终局对决；也可写事业、关系或身份的阶段。" className="mt-1.5 min-h-24 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label></div><div className="mt-4 grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">情绪走向<textarea value={outline.emotionalCurve} onChange={(event) => setOutline({ ...outline, emotionalCurve: event.target.value })} placeholder="例如：压抑开局 → 连续逆转 → 高潮爆发 → 余韵收束" className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="block text-sm font-medium">长期钩子<textarea value={outline.keyHooks} onChange={(event) => setOutline({ ...outline, keyHooks: event.target.value })} placeholder="贯穿全书、分阶段回收的谜题、承诺或悬念。" className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label></div></div><div className="space-y-4">{outline.stages.map((stage, index) => <article key={index} className="rounded-[18px] border border-border bg-workspace p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-medium">阶段 {index + 1}</h2>{outline.stages.length > 1 ? <button onClick={() => setOutline((current) => ({ ...current, stages: current.stages.filter((_, stageIndex) => stageIndex !== index) }))} className="text-xs text-destructive hover:underline">移除阶段</button> : null}</div><div className="mt-4 grid gap-4 md:grid-cols-2"><label className="block text-sm font-medium">阶段名称<input value={stage.title} onChange={(event) => updateStage(index, 'title', event.target.value)} placeholder="例如：开篇期" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label><label className="block text-sm font-medium">预计章节范围<input value={stage.chapterRange} onChange={(event) => updateStage(index, 'chapterRange', event.target.value)} placeholder="例如：第 1–80 章" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 outline-none focus:ring-2 focus:ring-brand" /></label></div><label className="mt-4 block text-sm font-medium">这一阶段要完成什么？<textarea value={stage.goal} onChange={(event) => updateStage(index, 'goal', event.target.value)} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">关键转折<textarea value={stage.turningPoint} onChange={(event) => updateStage(index, 'turningPoint', event.target.value)} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label><label className="mt-4 block text-sm font-medium">这一阶段暂时不要揭开什么？<textarea value={stage.forbiddenReveals} onChange={(event) => updateStage(index, 'forbiddenReveals', event.target.value)} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm outline-none focus:ring-2 focus:ring-brand" /></label></article>)}</div><div className="flex flex-wrap items-center gap-3"><button disabled={outline.stages.length >= 8} onClick={() => setOutline((current) => ({ ...current, stages: [...current.stages, { title: '', chapterRange: '', goal: '', turningPoint: '', forbiddenReveals: '' }] }))} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-hover disabled:opacity-50">新增阶段</button><button disabled={busy} onClick={() => void save()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '保存中…' : '保存全书大纲'}</button>{notice ? <p className="text-sm text-success">{notice}</p> : null}{error ? <p className="text-sm text-destructive">{error}</p> : null}</div></section>
}

function ChapterOutlinePanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const chapters = [...detail.chapters].sort((left, right) => right.sequence - left.sequence)
  const plannedCount = chapters.filter((chapter) => chapter.status === 'planned').length
  const units = detail.plotUnits || []
  const [editing, setEditing] = useState<Chapter | null | 'new'>(null)
  const [form, setForm] = useState({ title: '', summary: '', protagonistGoal: '', targetEmotion: '', keyChoice: '', characterChange: '', endingHook: '', plotUnitId: '', targetWords: '1800' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function open(chapter: Chapter | 'new') { const blueprint = chapter === 'new' ? {} : chapter.blueprint || {}; setEditing(chapter); setError(''); setForm({ title: chapter === 'new' ? `第${Math.max(0, ...chapters.map((item) => item.sequence)) + 1}章` : chapter.title, summary: blueprint.summary || (chapter === 'new' ? '' : chapter.outline || ''), protagonistGoal: blueprint.protagonistGoal || '', targetEmotion: blueprint.targetEmotion || '', keyChoice: blueprint.keyChoice || '', characterChange: blueprint.characterChange || '', endingHook: blueprint.endingHook || '', plotUnitId: chapter === 'new' ? (units.find((item) => item.status === 'active')?.id || units[0]?.id || '') : chapter.plotUnitId || '', targetWords: String(blueprint.targetWords || 1800) }) }
  async function save() { if (!form.title.trim() || !form.summary.trim()) { setError('请填写章节标题和本章事件'); return } if (!form.plotUnitId && !units.length) { setError('请先创建剧情单元'); return } setBusy(true); setError(''); const body = { title: form.title, summary: form.summary, protagonist_goal: form.protagonistGoal, target_emotion: form.targetEmotion, key_choice: form.keyChoice, character_change: form.characterChange, ending_hook: form.endingHook, plot_unit_id: form.plotUnitId, target_words: parseInt(form.targetWords) || 1800 }; try { if (editing === 'new') await kernelPost(`/api/novels/${detail.id}/chapter-blueprints`, body); else if (editing) await kernelPatch(`/api/novels/${detail.id}/chapter-blueprints/${editing.id}`, body); setEditing(null); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function remove(chapter: Chapter) { if (!window.confirm(`确定删除第${chapter.sequence}章细纲吗？`)) return; try { await kernelDelete(`/api/novels/${detail.id}/chapter-blueprints/${chapter.id}`); await onChanged() } catch (err) { setError(messageFrom(err)) } }
  async function deleteDraft(chapter: Chapter) { if (!window.confirm(`确定删除第${chapter.sequence}章草稿？章节将一并删除。`)) return; try { await kernelDelete(`/api/novels/${detail.id}/chapters/${chapter.id}/draft`); await onChanged() } catch (err) { setError(messageFrom(err)) } }
  async function discardDraft(chapter: Chapter) { if (!window.confirm(`废弃草稿后，第${chapter.sequence}章回退到待生成状态，细纲保留，可重新生成。确定废弃？`)) return; try { await kernelPost(`/api/novels/${detail.id}/chapters/${chapter.id}/draft/discard`); await onChanged() } catch (err) { setError(messageFrom(err)) } }
  return <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">滚动规划</p><h1 className="mt-1 text-lg font-semibold">章节细纲</h1><p className="mt-1 text-sm leading-6 text-muted-foreground">一次先规划接下来的一两章即可。使用下方 AI 建议生成可编辑细纲，写下一章会优先使用最靠前、尚未生成的细纲。</p>{plannedCount === 0 ? <p className="mt-4 rounded-xl bg-active p-3 text-sm text-muted-foreground">暂无待生成细纲。请先使用下方 AI 建议创建并确认。</p> : <p className="mt-4 rounded-xl border border-brand-border bg-brand-soft p-3 text-sm text-muted-foreground">当前有 {plannedCount} 章待生成细纲，可在下方"生成本章草稿"继续。</p>}</div><div className="space-y-3">{chapters.map((chapter) => <article key={chapter.id} className="rounded-[18px] border border-border bg-workspace p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-medium">第 {chapter.sequence} 章 · {chapter.title || '未命名章节'}</h2><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-body-foreground">{chapter.blueprint?.summary || chapter.outline || '本章尚未保存细纲。'}</p></div><div className="flex items-center gap-2"><span className="rounded-full bg-active px-2.5 py-1 text-xs text-muted-foreground">{chapterStatusLabel(chapter.status)}</span>{chapter.status === 'planned' ? <><button onClick={() => open(chapter)} className="rounded px-2 py-1 text-xs hover:bg-hover">编辑</button><button onClick={() => void remove(chapter)} className="rounded px-2 py-1 text-xs text-destructive hover:bg-hover">删除</button></> : null}{(chapter.status === 'drafting' || chapter.status === 'ready_for_author') ? <><button onClick={() => void discardDraft(chapter)} className="rounded px-2 py-1 text-xs hover:bg-hover">废弃草稿</button><button onClick={() => void deleteDraft(chapter)} className="rounded px-2 py-1 text-xs text-destructive hover:bg-hover">删除</button></> : null}</div></div>{chapter.blueprint ? <p className="mt-3 text-xs leading-5 text-muted-foreground">{[chapter.blueprint.protagonistGoal && `主角目标:${chapter.blueprint.protagonistGoal}`, chapter.blueprint.targetEmotion && `情绪:${chapter.blueprint.targetEmotion}`, chapter.blueprint.targetWords && `目标字数:${chapter.blueprint.targetWords}`, chapter.blueprint.endingHook && `钩子:${chapter.blueprint.endingHook}`].filter(Boolean).join(' · ')}</p> : null}</article>)}{chapters.length === 0 ? <p className="rounded-[18px] border border-dashed border-border bg-workspace p-8 text-center text-sm text-muted-foreground">还没有章节细纲。请使用下方的 AI 建议生成第一章细纲，再确认创建。</p> : null}</div>{editing ? <div className="fixed inset-0 z-50 flex items-center justify-center overflow-auto bg-black/30 p-4"><div className="w-full max-w-2xl rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"><div className="flex items-start justify-between"><div><h2 className="text-lg font-semibold">编辑章节细纲</h2><p className="mt-1 text-sm text-muted-foreground">可以在 AI 建议的基础上调整本章事件、选择和结尾钩子。</p></div><button onClick={() => setEditing(null)} className="rounded-lg p-1 hover:bg-hover"><X className="size-4" /></button></div><div className="mt-5 grid gap-4 md:grid-cols-2"><label className="text-sm font-medium">章节标题<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="text-sm font-medium">所属剧情单元<select value={form.plotUnitId} onChange={(event) => setForm({ ...form, plotUnitId: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2"><option value="">使用当前进行单元</option>{units.map((unit) => <option key={unit.id} value={unit.id}>第{unit.sequence}段 · {unit.title}</option>)}</select></label></div><label className="mt-4 block text-sm font-medium">这一章要发生什么？<textarea value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} className="mt-1.5 min-h-28 w-full rounded-xl border bg-surface p-3 text-sm" /></label><div className="mt-4 grid gap-4 md:grid-cols-2"><label className="text-sm font-medium">主角目标<input value={form.protagonistGoal} onChange={(event) => setForm({ ...form, protagonistGoal: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="text-sm font-medium">目标情绪<input value={form.targetEmotion} onChange={(event) => setForm({ ...form, targetEmotion: event.target.value })} placeholder="紧张、期待、爽感…" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label></div><label className="mt-4 block text-sm font-medium">目标字数<input value={form.targetWords} onChange={(event) => setForm({ ...form, targetWords: event.target.value })} inputMode="numeric" placeholder="500 ~ 5000" className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="mt-4 block text-sm font-medium">主角要做出的关键选择<textarea value={form.keyChoice} onChange={(event) => setForm({ ...form, keyChoice: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm" /></label><label className="mt-4 block text-sm font-medium">人物或关系的变化<textarea value={form.characterChange} onChange={(event) => setForm({ ...form, characterChange: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm" /></label><label className="mt-4 block text-sm font-medium">结尾钩子<textarea value={form.endingHook} onChange={(event) => setForm({ ...form, endingHook: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-xl border bg-surface p-3 text-sm" /></label>{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}<div className="mt-6 flex justify-end gap-2"><button onClick={() => setEditing(null)} className="rounded-lg px-4 py-2 text-sm hover:bg-hover">取消</button><button disabled={busy} onClick={() => void save()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '保存中…' : '保存章节细纲'}</button></div></div></div> : null}</section>
}

function PlotUnitSuggestionPanel({ detail, onChanged, open, onClose }: { detail: NovelDetail; onChanged: () => Promise<void>; open: boolean; onClose: () => void }) {
  const [instruction, setInstruction] = useState('')
  const [suggestion, setSuggestion] = useState<{ title: string; promise: string; protagonist_goal: string; obstacle?: string; payoff?: string; forbidden_reveals?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function generate() { setBusy(true); setError(''); try { const data = await kernelPost<{ suggestion: { title: string; promise: string; protagonist_goal: string; obstacle?: string; payoff?: string; forbidden_reveals?: string } }>(`/api/novels/${detail.id}/plot-units/suggest`, { instruction }); setSuggestion(data.suggestion) } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function adopt() { if (!suggestion?.title.trim()) return; setBusy(true); setError(''); try { await kernelPost(`/api/novels/${detail.id}/plot-units`, { title: suggestion.title, promise: suggestion.promise || '', protagonist_goal: suggestion.protagonist_goal || '', obstacle: suggestion.obstacle || '', payoff: suggestion.payoff || '', forbidden_reveals: suggestion.forbidden_reveals || '', status: 'planned' }); setSuggestion(null); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  if (!open) return null
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
    <section className="flex max-h-[calc(100dvh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-[22px] border border-brand-border bg-workspace shadow-[var(--shadow-floating-strong)]">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-6 py-5"><div><p className="text-xs font-medium text-brand">AI 辅助规划</p><h2 className="mt-1 text-lg font-semibold">剧情单元建议生成</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">会综合本书方向、全书大纲、既有剧情、人物关系和未解决伏笔给出下一段建议；你编辑并确认后才会创建。</p></div><button onClick={onClose} className="rounded-lg p-1.5 hover:bg-hover" title="关闭"><X className="size-4" /></button></div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5"><textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="例如：下一段要把主角推入更高层级的冲突，并推进与师父的关系。" className="min-h-24 w-full rounded-xl border bg-surface p-3 text-sm" /><button disabled={busy} onClick={() => void generate()} className="mt-3 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-foreground shadow-sm hover:opacity-90 disabled:opacity-50">{busy ? '生成中…' : '生成剧情单元建议'}</button>{suggestion ? <div className="mt-4 rounded-xl bg-brand-soft p-4"><label className="block text-sm font-medium">剧情单元名称<input value={suggestion.title} onChange={(event) => setSuggestion({ ...suggestion, title: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="mt-3 block text-sm font-medium">读者期待<textarea value={suggestion.promise} onChange={(event) => setSuggestion({ ...suggestion, promise: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label><label className="mt-3 block text-sm font-medium">主角目标<textarea value={suggestion.protagonist_goal} onChange={(event) => setSuggestion({ ...suggestion, protagonist_goal: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label><label className="mt-3 block text-sm font-medium">主要阻碍<textarea value={suggestion.obstacle || ''} onChange={(event) => setSuggestion({ ...suggestion, obstacle: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label><label className="mt-3 block text-sm font-medium">阶段回报<textarea value={suggestion.payoff || ''} onChange={(event) => setSuggestion({ ...suggestion, payoff: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label><label className="mt-3 block text-sm font-medium">暂不揭示<textarea value={suggestion.forbidden_reveals || ''} onChange={(event) => setSuggestion({ ...suggestion, forbidden_reveals: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label></div> : null}{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</div>
      {suggestion ? <div className="flex shrink-0 justify-end gap-2 border-t border-border bg-workspace px-6 py-4"><button disabled={busy || !suggestion.title.trim()} onClick={() => void adopt()} className="rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">确认创建</button><button onClick={() => setSuggestion(null)} className="rounded-lg px-3 py-2 text-sm hover:bg-hover">放弃建议</button></div> : null}
    </section>
  </div>
}

function PlotUnitWorkspace({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const [suggestionOpen, setSuggestionOpen] = useState(false)
  return <section className="space-y-5"><OutlinePanel detail={detail} onChanged={onChanged} onRequestSuggestion={() => setSuggestionOpen(true)} /><PlotUnitSuggestionPanel detail={detail} onChanged={onChanged} open={suggestionOpen} onClose={() => setSuggestionOpen(false)} /></section>
}

function ChapterSuggestionPanel({ detail, onChanged }: { detail: NovelDetail; onChanged: () => Promise<void> }) {
  const units = detail.plotUnits || []
  const [unitId, setUnitId] = useState(units.find((unit) => unit.status === 'active')?.id || units[0]?.id || '')
  const [suggestion, setSuggestion] = useState<{ title: string; summary: string; ending_hook: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function generate() { setBusy(true); setError(''); try { const data = await kernelPost<{ suggestions: Array<{ title: string; summary: string; ending_hook: string }> }>(`/api/novels/${detail.id}/chapter-blueprints/suggest`, { plot_unit_id: unitId, chapter_count: 1 }); setSuggestion(data.suggestions[0] || null) } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  async function adopt() { if (!suggestion?.title.trim() || !suggestion.summary.trim()) return; setBusy(true); setError(''); try { await kernelPost(`/api/novels/${detail.id}/chapter-blueprints`, { title: suggestion.title, summary: suggestion.summary, ending_hook: suggestion.ending_hook || '', plot_unit_id: unitId }); setSuggestion(null); await onChanged() } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) } }
  return <section className="rounded-[18px] border border-brand-border bg-brand-soft p-6 shadow-sm"><p className="text-xs font-semibold text-brand">从这里开始</p><h2 className="mt-1 text-lg font-semibold">AI 生成下一章细纲</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">选择承接的剧情单元，AI 会生成一章可编辑细纲；确认创建前不会写入章节。</p><div className="mt-4 flex flex-wrap items-center gap-3"><select value={unitId} onChange={(event) => setUnitId(event.target.value)} className="w-full max-w-xl rounded-lg border border-brand-border bg-surface px-3 py-2 text-sm">{units.map((unit) => <option key={unit.id} value={unit.id}>第{unit.sequence}段 · {unit.title}</option>)}</select><button disabled={busy || !unitId} onClick={() => void generate()} className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-foreground shadow-sm hover:opacity-90 disabled:opacity-50">{busy ? '生成中…' : '生成章节细纲建议'}</button></div>{suggestion ? <div className="mt-4 rounded-xl border border-brand-border bg-surface p-4"><label className="block text-sm font-medium">章节标题<input value={suggestion.title} onChange={(event) => setSuggestion({ ...suggestion, title: event.target.value })} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="mt-3 block text-sm font-medium">本章事件<textarea value={suggestion.summary} onChange={(event) => setSuggestion({ ...suggestion, summary: event.target.value })} className="mt-1.5 min-h-28 w-full rounded-lg border bg-surface p-3" /></label><label className="mt-3 block text-sm font-medium">结尾钩子（可选）<textarea value={suggestion.ending_hook || ''} onChange={(event) => setSuggestion({ ...suggestion, ending_hook: event.target.value })} className="mt-1.5 min-h-20 w-full rounded-lg border bg-surface p-3" /></label><div className="mt-3 flex gap-2"><button disabled={busy || !suggestion.title.trim() || !suggestion.summary.trim()} onClick={() => void adopt()} className="rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">确认创建</button><button onClick={() => setSuggestion(null)} className="rounded-lg px-3 py-2 text-sm hover:bg-hover">放弃建议</button></div></div> : null}{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</section>
}

function LegacyChapterOutlineWorkspace({ detail, onChanged, onOpenDrafts }: { detail: NovelDetail; onChanged: () => Promise<void>; onOpenDrafts: () => void }) {
  const planned = [...detail.chapters].filter((chapter) => chapter.status === 'planned').sort((left, right) => left.sequence - right.sequence)
  const [chapterId, setChapterId] = useState(planned[0]?.id || '')
  const [characters, setCharacters] = useState<Character[]>([])
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [foreshadows, setForeshadows] = useState<Foreshadow[]>([])
  const [selectedCharacterIds, setSelectedCharacterIds] = useState<string[]>([])
  const [selectedRelationshipIds, setSelectedRelationshipIds] = useState<string[]>([])
  const [selectedForeshadowIds, setSelectedForeshadowIds] = useState<string[]>([])
  const [resourcesOpen, setResourcesOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  useEffect(() => setChapterId(planned[0]?.id || ''), [detail.id, planned[0]?.id])
  useEffect(() => { void Promise.all([
    kernelGet<Character[]>(`/api/novels/${detail.id}/characters`),
    kernelGet<Relationship[]>(`/api/novels/${detail.id}/relationships`),
    kernelGet<Foreshadow[]>(`/api/novels/${detail.id}/foreshadows?status=active`),
  ]).then(([people, links, clues]) => { setCharacters(people); setRelationships(links); setForeshadows(clues) }).catch((err) => setError(messageFrom(err))) }, [detail.id])
  function toggle(id: string, selected: string[], setSelected: (value: string[]) => void) { setSelected(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]) }
  async function generate() {
    if (!chapterId) return
    setBusy(true); setNotice(''); setError('')
    try {
      const characterNames = characters.filter((item) => selectedCharacterIds.includes(item.id)).map((item) => item.name)
      await kernelPost(`/api/novels/${detail.id}/chapters/${chapterId}/generate`, {
        target_words: 1800,
        memory_focus: characterNames,
        resource_focus: { character_names: characterNames, relationship_ids: selectedRelationshipIds, foreshadow_ids: selectedForeshadowIds },
      })
      setNotice('草稿已生成。')
      await onChanged()
    } catch (err) { setError(messageFrom(err)) } finally { setBusy(false) }
  }
  const resources = [...characters.map((item) => ({ id: item.id, label: item.name, detail: item.currentState || item.identity || '人物状态', selected: selectedCharacterIds, setSelected: setSelectedCharacterIds })), ...relationships.map((item) => ({ id: item.id, label: `${item.fromCharacterName || '人物'} · ${item.relationType || '关系'} · ${item.toCharacterName || '人物'}`, detail: item.currentState || '人物关系', selected: selectedRelationshipIds, setSelected: setSelectedRelationshipIds })), ...foreshadows.map((item) => ({ id: item.id, label: item.title, detail: item.content || '伏笔与线索', selected: selectedForeshadowIds, setSelected: setSelectedForeshadowIds }))]
  const selectedResourceCount = selectedCharacterIds.length + selectedRelationshipIds.length + selectedForeshadowIds.length
  const selectedChapter = planned.find((chapter) => chapter.id === chapterId)
  if (!planned.length) return null
  return <section className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">从细纲生成草稿</p><h2 className="mt-1 text-lg font-semibold">准备写这一章</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">先选择已经确认的细纲；系统会自动承接已发生事实。只有需要特别强调的内容，才勾选重点资源。</p><div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]"><label className="block text-sm font-medium">1. 选择章节<select value={chapterId} onChange={(event) => setChapterId(event.target.value)} className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2 text-sm">{planned.map((chapter) => <option key={chapter.id} value={chapter.id}>第{chapter.sequence}章 · {chapter.title}</option>)}</select></label><button onClick={() => setResourcesOpen((value) => !value)} className={`self-end rounded-lg border px-3 py-2 text-sm hover:bg-hover ${selectedResourceCount ? 'border-brand-border bg-brand-soft' : 'border-border'}`}>{resourcesOpen ? '收起重点资源' : selectedResourceCount ? `重点资源 ${selectedResourceCount} 项` : '2. 选择重点资源（可选）'}</button></div>{selectedChapter ? <div className="mt-3 rounded-xl bg-active p-4"><p className="text-sm font-medium">第{selectedChapter.sequence}章 · {selectedChapter.title}</p><p className="mt-1 text-sm leading-6 text-muted-foreground">{selectedChapter.blueprint?.summary || selectedChapter.outline}</p></div> : null}{resourcesOpen ? <div className="mt-4 rounded-xl border border-border bg-active p-4"><p className="text-sm font-medium">本章重点资源</p><p className="mt-1 text-xs text-muted-foreground">勾选后会随细纲进入生成上下文，适合处理特定人物、关系或伏笔。</p><div className="mt-3 grid gap-2 md:grid-cols-2">{resources.map((item) => <label key={item.id} className="flex cursor-pointer gap-2 rounded-lg bg-surface px-3 py-2 hover:bg-hover"><input type="checkbox" checked={item.selected.includes(item.id)} onChange={() => toggle(item.id, item.selected, item.setSelected)} className="mt-0.5" /><span className="min-w-0"><span className="block truncate text-sm font-medium">{item.label}</span><span className="block truncate text-xs text-muted-foreground">{item.detail}</span></span></label>)}</div>{resources.length === 0 ? <p className="mt-3 text-xs text-muted-foreground">暂无可勾选资源；可先在世界与人物、人物关系或伏笔与线索中完善。</p> : null}</div> : null}{selectedResourceCount ? <p className="mt-3 rounded-lg border border-brand-border bg-brand-soft px-3 py-2 text-xs text-muted-foreground">已选择 {selectedResourceCount} 项重点资源：它们只会在本次草稿生成时作为额外约束带入，不会修改现有故事事实。</p> : null}<div className="mt-5 flex flex-wrap items-center gap-3"><button disabled={busy} onClick={() => void generate()} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{busy ? '正在生成草稿…' : '生成本章草稿'}</button><p className="text-xs text-muted-foreground">生成后可在“草稿与审校”查看、修改并采纳。</p></div>{notice ? <p className="mt-3 flex items-center gap-3 text-sm text-success">{notice}<button onClick={onOpenDrafts} className="rounded-lg border border-brand-border px-3 py-1.5 text-xs font-medium hover:bg-brand-soft">去草稿与审校</button></p> : null}{error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}</section>
}

function ChapterOutlineWorkspace({ detail, onChanged, onOpenDrafts }: { detail: NovelDetail; onChanged: () => Promise<void>; onOpenDrafts: () => void }) {
  return <section className="space-y-5"><ChapterSuggestionPanel detail={detail} onChanged={onChanged} /><ChapterOutlinePanel detail={detail} onChanged={onChanged} /><LegacyChapterOutlineWorkspace detail={detail} onChanged={onChanged} onOpenDrafts={onOpenDrafts} /></section>
}

function LibraryPage({ onLogout }: { onLogout: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [mode, setMode] = useState<'writing' | 'script'>(() => searchParams.get('mode') === 'script' ? 'script' : 'writing')
  const [novels, setNovels] = useState<Novel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [createMode, setCreateMode] = useState<'writing' | 'script' | null>(null)
  const navigate = useNavigate()
  async function reload(selected = mode) { setLoading(true); setError(''); try { setNovels(await kernelGet<Novel[]>(`/api/novels?mode=${selected}`)) } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) } }
  useEffect(() => { void reload(mode) }, [mode])
  function created(novel: Novel) { setCreateMode(null); navigate(`/workbench?id=${encodeURIComponent(novel.id)}`) }
  return (
    <div className="min-h-full">
      <header className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2 font-semibold"><span className="flex size-8 items-center justify-center rounded-lg bg-brand font-bold text-brand-foreground">N</span>Novel</Link>
        <div className="flex items-center gap-2">
          <button onClick={() => setCreateMode(mode)} className="flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-sm font-medium text-primary-foreground"><Plus className="size-4" />{mode === 'writing' ? '新建小说' : '导入剧本'}</button>
          <button onClick={() => navigate('/settings')} className="rounded-lg p-2 text-muted-foreground hover:bg-hover" title="应用设置"><Settings className="size-4" /></button>
          <button onClick={() => { logout(); onLogout() }} className="rounded-lg p-2 text-muted-foreground hover:bg-hover hover:text-destructive" title="退出登录"><LogOut className="size-4" /></button>
        </div>
      </header>
      <div className="mx-auto max-w-[1440px] px-6 pb-10">
        <section className="rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-workspace)]">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div><p className="text-sm text-muted-foreground">我的创作空间</p><h1 className="mt-1 text-2xl font-semibold">小说书架</h1></div>
            <div className="flex rounded-lg bg-active p-1">
              <button onClick={() => { setMode('writing'); setSearchParams({ mode: 'writing' }) }} className={`rounded-md px-4 py-2 text-sm ${mode === 'writing' ? 'bg-surface shadow-sm' : 'text-muted-foreground'}`}>写作</button>
              <button onClick={() => { setMode('script'); setSearchParams({ mode: 'script' }) }} className={`rounded-md px-4 py-2 text-sm ${mode === 'script' ? 'bg-surface shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>剧本</button>
            </div>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">{mode === 'writing' ? '新建、续写和修订你的原创小说。' : '导入已有小说，在指定章节与人物进行临时对话。'}</p>
        </section>
        {error ? <p className="mt-4 rounded-xl border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
        <section className="mt-6 grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
          {loading ? <div className="col-span-full flex min-h-60 items-center justify-center text-muted-foreground"><Loader2 className="mr-2 size-4 animate-spin" />正在读取书架</div> : null}
          {!loading ? novels.map((novel) => (
            <article key={novel.id} className="group relative flex min-h-[260px] flex-col rounded-[18px] border border-border bg-workspace p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-floating)]">
              <div className="flex items-start justify-between"><div className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-brand"><BookOpen className="size-5" /></div><button onClick={async () => { if (!window.confirm(`确定删除《${novel.title}》及其所有数据吗？`)) return; try { await kernelDelete(`/api/novels/${novel.id}`); await reload(mode) } catch (err) { setError(messageFrom(err)) } }} className="rounded-lg p-1.5 text-muted-foreground hover:bg-hover hover:text-destructive" title="删除作品"><X className="size-4" /></button></div>
              <div className="mt-5"><h2 className="line-clamp-2 text-lg font-semibold">{novel.title}</h2><p className="mt-1 text-sm text-muted-foreground">{novel.genre || '未设置题材'} · {novel.targetPlatform || '番茄'}</p></div>
              <p className="mt-3 min-h-10 text-xs leading-5 text-muted-foreground">{novel.corePromise || (mode === 'script' ? '正在建立人物档案与证据索引。' : '等待继续完善读者契约与剧情单元。')}</p>
              <div className="mt-auto flex items-end justify-between gap-3 border-t border-border pt-4 text-xs text-muted-foreground"><div className="min-w-0 leading-5">{mode === 'writing' ? <><p>目标：{formatWords(novel.targetWords)}</p><p>已写：{formatWords(novel.writtenWords)}</p></> : <p>{novel.importedChapterCount || 0} 章 · {displayStatus(novel.status, '已就绪')}</p>}</div><button onClick={() => navigate(`/workbench?id=${encodeURIComponent(novel.id)}`)} className="shrink-0 flex items-center gap-1 font-medium text-foreground">{mode === 'script' ? '进入剧本' : '进入工作台'}<ChevronRight className="size-4" /></button></div>
            </article>
          )) : null}
          {!loading && novels.length === 0 ? (
            <div className="col-span-full flex min-h-64 flex-col items-center justify-center rounded-[18px] border border-dashed border-border bg-workspace"><Library className="size-7 text-muted-foreground" /><h2 className="mt-3 font-semibold">{mode === 'writing' ? '开始第一部小说' : '还没有剧本'}</h2><p className="mt-1 text-sm text-muted-foreground">{mode === 'writing' ? '创建一本书，开始规划与写作。' : '导入已有小说，即可与其中人物对话。'}</p><button onClick={() => setCreateMode(mode)} className="mt-4 rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground">{mode === 'writing' ? '新建小说' : '导入剧本'}</button></div>
          ) : null}
        </section>
      </div>
      {createMode ? <CreateDialog mode={createMode} onClose={() => setCreateMode(null)} onCreated={created} /> : null}
    </div>
  )
}

function WorkbenchPage() {
  const [params] = useSearchParams(); const novelId = params.get('id') || ''; const initialSection = params.get('section') || ''; const initialExperienceId = params.get('experience') || ''
  const [detail, setDetail] = useState<NovelDetail | null>(null); const [characters, setCharacters] = useState<Character[]>([]); const [tasks, setTasks] = useState<Task[]>([]); const [experienceCount, setExperienceCount] = useState(0)
  const [section, setSection] = useState(initialSection || 'overview'); const [selectedChapter, setSelectedChapterState] = useState<Chapter | null>(null); const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null); const [memoryFocusIds, setMemoryFocusIds] = useState<string[]>([])
  // 保留 API 原始 status（accepted/planned/...）；展示文案在渲染时用 chapterStatusLabel，勿在此处本地化，否则「已写章节」的 status==='accepted' 判断永远失败。
  const setSelectedChapter = (next: SetStateAction<Chapter | null>) => setSelectedChapterState((current) => {
    const selected = typeof next === 'function' ? next(current) : next
    return selected ?? null
  })
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [chatInput, setChatInput] = useState(''); const [messages, setMessages] = useState<DialogueMessage[]>([]); const [chatting, setChatting] = useState(false); const [taskOpen, setTaskOpen] = useState(false)
  const navigate = useNavigate()
  async function reload() { if (!novelId) return; setLoading(true); setError(''); try { const [book, people, runs] = await Promise.all([kernelGet<NovelDetail>(`/api/novels/${novelId}`), kernelGet<Character[]>(`/api/novels/${novelId}/characters`), kernelGet<{ list: Task[] } | Task[]>('/api/tasks')]); setDetail({ ...book, status: displayStatus(book.status, '进行中') }); setSelectedChapter((current) => { const accepted = book.chapters.filter((chapter) => chapter.status === 'accepted').sort((a, b) => a.sequence - b.sequence); if (current) { const refreshed = book.chapters.find((chapter) => chapter.id === current.id); if (refreshed) return refreshed } return accepted.at(-1) || book.chapters.at(-1) || null }); setCharacters(people); setSelectedCharacter((current) => current || people[0] || null); setTasks(Array.isArray(runs) ? runs : runs.list || []); if (book.sourceMode === 'script') { const experiences = await kernelGet<any[]>(`/api/novels/${novelId}/experiences`); setExperienceCount(experiences.length) } else setExperienceCount(0) } catch (err) { setError(messageFrom(err)) } finally { setLoading(false) } }
  async function reloadTasks() { try { const runs = await kernelGet<{ list: Task[] } | Task[]>('/api/tasks'); setTasks(Array.isArray(runs) ? runs : runs.list || []) } catch (err) { setError(messageFrom(err)) } }
  useEffect(() => { void reload() }, [novelId])
  useEffect(() => { setSection(initialSection || 'overview') }, [initialSection])
  const script = detail?.sourceMode === 'script'
  const openExperienceEnter = (experienceId?: string) => {
    setSection('experience-enter')
    const targetExperienceId = experienceId || initialExperienceId
    const experience = targetExperienceId ? `&experience=${encodeURIComponent(targetExperienceId)}` : ''
    navigate(`/workbench?id=${encodeURIComponent(novelId)}&section=experience-enter${experience}`)
  }
  const memoryFocusNames = characters.filter((item) => memoryFocusIds.includes(item.id)).map((item) => item.name)
  const nav = [{ id: 'overview', label: script ? '剧本概览' : '创作进度' }, { id: 'settings', label: '本书方向' }, { id: 'full-outline', label: '全书大纲' }, { id: 'memory', label: '世界与人物' }, { id: 'outline', label: '故事创作' }, { id: 'facts', label: '伏笔与线索' }, { id: 'graph', label: '记忆星图' }, { id: 'characters', label: '唠个嗑' }, { id: 'reference', label: '参考作品' }, { id: 'packs', label: '能力包' }]
  const groups: WorkbenchGroup[] = [
    { id: 'progress', label: script ? '剧本概览' : '创作进度', icon: Sparkles, target: 'overview' },
    ...(!script ? [{ id: 'world', label: '世界与人物', icon: Users, target: 'memory', children: [{ id: 'memory', label: '人物档案' }, { id: 'relationships', label: '人物关系' }, { id: 'graph', label: '记忆星图' }, { id: 'candidates', label: '人物候选' }] }] : []),
    ...(!script ? [
      { id: 'story-creation', label: '故事创作', icon: FileText, target: 'outline', children: [{ id: 'settings', label: '本书方向' }, { id: 'full-outline', label: '全书大纲' }, { id: 'outline', label: '剧情单元' }, { id: 'facts', label: '伏笔与线索' }, { id: 'chapter-outlines', label: '章节细纲' }, { id: 'drafts', label: '草稿与审校' }] },
    ] : []),
    { id: 'content', label: script ? '剧本正史' : '故事内容', icon: CheckCircle2, target: 'chapters', children: script ? undefined : [{ id: 'chapters', label: '已写章节' }] },
    ...(script ? [{ id: 'experience', label: '副本体验', icon: Sparkles, target: 'experience', children: [{ id: 'experience', label: '副本列表' }, { id: 'experience-enter', label: '进入副本' }] }] : []),
    ...(!script ? [{ id: 'chat', label: '唠个嗑', icon: MessageCircle, target: 'chat' }] : []),
    ...(!script ? [{ id: 'reference', label: '参考作品', icon: BookOpen, target: 'reference', unavailable: true }] : []),
    ...(!script ? [{ id: 'packs', label: '能力包', icon: Bot, target: 'packs' }] : []),
  ]
  async function sendMessage(event: FormEvent) { event.preventDefault(); if (!selectedCharacter || !chatInput.trim() || !detail) return; const message = chatInput.trim(); setChatInput(''); setMessages((old) => [...old, { role: 'user', content: message }]); setChatting(true); try { const response = await kernelPost<{ reply: string }>(`/api/novels/${detail.id}/characters/${selectedCharacter.id}/script-dialogue`, { message, source_segment_order: selectedChapter?.sourceSegmentOrder || selectedChapter?.sequence || 0, history: messages }); setMessages((old) => [...old, { role: 'assistant', content: response.reply }]) } catch (err) { setMessages((old) => [...old, { role: 'assistant', content: `请求失败：${messageFrom(err)}` }]) } finally { setChatting(false) } }
  if (!novelId) return <Unavailable title="未选择小说" description="请先从书架选择一本作品进入工作台。" />
  if (loading) return <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="mr-2 size-4 animate-spin" />正在载入工作台</div>
  if (!detail) return <div className="m-6"><Unavailable title="小说读取失败" description={error || '该小说不存在，或当前登录用户没有访问权限。'} /></div>
  if ((section === 'experience' || section === 'experience-enter') && script) return <div className="flex h-full min-h-0 flex-col"><header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-workspace px-4"><button onClick={() => navigate(`/workbench?id=${encodeURIComponent(novelId)}&section=experience`)} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm hover:bg-hover"><ArrowLeft className="size-4" />返回剧本工作台</button><div className="text-sm font-semibold">{detail.title} · 副本体验</div><span className="w-24" /></header><div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)]"><WorkbenchSidebar groups={groups} section={section} onSelect={setSection} /><main className="min-w-0 overflow-auto bg-background p-5"><ExperiencePanel novel={detail} initialSnapshotId={initialExperienceId || undefined} enterMode={section === "experience-enter"} onEnter={openExperienceEnter} /></main></div></div>
  const taskPanel = <section className="rounded-[18px] border border-border bg-workspace"><header className="flex items-center justify-between border-b border-border p-5"><div><h1 className="font-semibold">后台任务</h1><p className="mt-1 text-xs text-muted-foreground">导入、生成和分析会在后台完成；刷新只读取任务状态。</p></div><button onClick={() => void reloadTasks()} className="rounded-lg p-2 hover:bg-hover" title="刷新任务"><RefreshCw className="size-4" /></button></header><div className="space-y-3 p-5">{tasks.map((task) => <article key={task.id} className="rounded-xl border border-border p-4"><div className="flex justify-between gap-3"><div><p className="font-medium">{task.label || displayTaskType(task.type)}</p><p className="mt-1 text-xs text-muted-foreground">{displayTaskStage(task.stage) || displayTaskStatus(task.status)}{task.traceId ? ` · ${task.traceId}` : ''}</p>{task.error ? <p className="mt-2 text-xs text-destructive">{task.error}</p> : null}</div><div className="flex items-start gap-2"><span className="rounded-full bg-active px-2 py-1 text-xs">{displayTaskStatus(task.status)}</span>{task.status === 'failed' ? <button onClick={() => void kernelPost(`/api/tasks/${task.id}/retry`).then(reloadTasks).catch((err) => setError(messageFrom(err)))} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-hover">重试</button> : null}{['queued', 'running', 'cancel_requested'].includes(task.status) ? <button onClick={() => void kernelPost(`/api/tasks/${task.id}/cancel`).then(reloadTasks).catch((err) => setError(messageFrom(err)))} className="rounded-md px-2 py-1 text-xs text-destructive hover:bg-hover">停止</button> : null}</div></div></article>)}{tasks.length === 0 ? <p className="text-sm text-muted-foreground">暂无任务。</p> : null}</div></section>
  const body = section === 'overview' ? <section className="space-y-5"><div className="rounded-[18px] border border-border bg-workspace p-6"><p className="text-xs font-medium text-muted-foreground">{script ? '剧本进度' : '创作进度'}</p><h1 className="mt-1 text-2xl font-semibold">{detail.title}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{detail.corePromise || (script ? '正在从已导入正文建立人物与故事事实。' : '先到“本书方向”说清这本书带给读者什么体验。')}</p><div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-active p-3"><p className="text-xs text-muted-foreground">章节</p><p className="mt-1 font-semibold">{detail.chapters.length} 章</p></div><div className="rounded-xl bg-active p-3"><p className="text-xs text-muted-foreground">{script ? '副本个数' : '人物'}</p><p className="mt-1 font-semibold">{script ? experienceCount : characters.length} {script ? '个' : '位'}</p></div><div className="rounded-xl bg-active p-3"><p className="text-xs text-muted-foreground">当前状态</p><p className="mt-1 font-semibold">{detail.status || '进行中'}</p></div></div></div><div className="rounded-[18px] border border-border bg-workspace p-6"><h2 className="font-semibold">接下来可以做什么</h2><div className="mt-4 grid gap-3 md:grid-cols-2"><button onClick={() => setSection(script ? 'experience' : 'write')} className="rounded-xl border border-border p-4 text-left hover:bg-hover"><FileText className="size-4" /><p className="mt-2 font-medium">{script ? '进入剧本体验' : '写下一章'}</p><p className="mt-1 text-xs text-muted-foreground">{script ? '选择章节范围并进入一个局部副本体验。' : '根据这一章的目标生成或继续完成正文。'}</p></button><button onClick={() => setSection(script ? 'memory' : 'outline')} className={script ? 'hidden' : 'rounded-xl border border-border p-4 text-left hover:bg-hover'}><MessageCircle className="size-4" /><p className="mt-2 font-medium">{script ? '查看人物事实' : '安排后续剧情'}</p><p className="mt-1 text-xs text-muted-foreground">{script ? '查看对话依据的原文证据。' : '确定接下来一段剧情的目标、阻碍和回报。'}</p></button></div></div></section> : section === 'chapters' ? (() => { const writtenChapters = detail.chapters.filter((chapter) => chapter.status === 'accepted').sort((a, b) => a.sequence - b.sequence); const activeChapter = pickActiveWrittenChapter(detail.chapters, selectedChapter?.id); return <section className="grid min-h-[620px] grid-cols-[250px_minmax(0,1fr)] overflow-hidden rounded-[18px] border border-border bg-workspace"><aside className="border-r border-border p-3"><p className="mb-2 px-2 text-xs font-medium text-muted-foreground">已写章节 · {writtenChapters.length}</p><div className="space-y-1">{writtenChapters.map((chapter) => <button key={chapter.id} title={chapter.title} onClick={() => setSelectedChapter(chapter)} className={`block w-full truncate rounded-lg px-3 py-2 text-left text-sm ${activeChapter?.id === chapter.id ? 'bg-active font-medium' : 'hover:bg-hover'}`}>第{chapter.sequence}章 · {chapter.title}</button>)}{writtenChapters.length === 0 ? <p className="px-2 py-4 text-xs text-muted-foreground">暂无已采纳正文。</p> : null}</div></aside><article className="min-w-0 p-7">{activeChapter ? <><h1 className="text-xl font-semibold">第{activeChapter.sequence}章 {activeChapter.title}</h1><div className="mt-6 whitespace-pre-wrap text-[15px] leading-8 text-body-foreground">{activeChapter.body || '本章暂无正文。'}</div></> : <p className="text-sm text-muted-foreground">采纳草稿后，正文将在此展示。</p>}</article></section> })() : section === 'revision' ? <ChapterRevisionPanel detail={detail} onChanged={reload} /> : section === 'characters' && script ? <section className="grid min-h-[620px] grid-cols-[250px_minmax(0,1fr)] overflow-hidden rounded-[18px] border border-border bg-workspace"><aside className="border-r border-border p-3"><p className="mb-2 px-2 text-xs font-medium text-muted-foreground">选择对话人物</p><div className="space-y-1">{characters.map((item) => <button key={item.id} onClick={() => { setSelectedCharacter(item); setMessages([]) }} className={`block w-full rounded-lg px-3 py-2 text-left ${selectedCharacter?.id === item.id ? 'bg-active' : 'hover:bg-hover'}`}><p className="truncate text-sm font-medium">{item.name}</p><p className="truncate text-xs text-muted-foreground">{item.currentState || item.status || '人物记忆已建立'}</p></button>)}</div></aside><div className="flex min-w-0 flex-col"><header className="border-b border-border px-6 py-4"><p className="font-semibold">与 {selectedCharacter?.name || '人物'} 对话</p><p className="mt-1 text-xs text-muted-foreground">时间点：{selectedChapter ? `第${selectedChapter.sequence}章后` : '最新章节'} · 对话不会修改小说正史</p></header><div className="flex-1 space-y-4 overflow-auto p-6">{messages.length === 0 ? <div className="rounded-xl bg-active p-4 text-sm text-muted-foreground">向人物打个招呼吧。回复仅依据已验证记忆和当前章节前的正文证据。</div> : messages.map((item, index) => <div key={index} className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 ${item.role === 'user' ? 'ml-auto bg-foreground text-primary-foreground' : 'bg-active text-body-foreground'}`}>{item.content}</div>)}{chatting ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />人物正在回应…</div> : null}</div><form onSubmit={sendMessage} className="border-t border-border p-4"><div className="flex gap-2"><input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder={`对 ${selectedCharacter?.name || '人物'} 说些什么…`} className="min-w-0 flex-1 rounded-lg border bg-surface px-3 py-2.5 outline-none focus:ring-2 focus:ring-brand" /><button disabled={!selectedCharacter || chatting} className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">发送</button></div></form></div></section> : section === 'characters' || section === 'memory' ? <MemoryEventsPanel detail={detail} characters={characters} /> : section === 'tasks' ? taskPanel : <Unavailable title={nav.find((item) => item.id === section)?.label || '功能'} description="该界面已按新版工作台保留；它依赖 new_novel 的专属后端能力，当前 Novel 后端尚未提供对应实现。" />
  const workspaceBody = section === 'graph' ? <MemoryGraphPanel detail={detail} characters={characters} focusIds={memoryFocusIds} onFocusIdsChange={setMemoryFocusIds} /> : section === 'relationships' ? <RelationshipsPanel detail={detail} characters={characters} /> : section === 'facts' ? <ForeshadowPanel detail={detail} /> : section === 'settings' ? <BookSetupPanel detail={detail} onChanged={reload} /> : section === 'full-outline' ? <FullOutlinePanel detail={detail} onChanged={reload} /> : section === 'outline' ? <PlotUnitWorkspace detail={detail} onChanged={reload} /> : section === 'chapter-outlines' || section === 'write' ? <ChapterOutlineWorkspace detail={detail} onChanged={reload} onOpenDrafts={() => setSection('drafts')} /> : section === 'drafts' || section === 'results' || section === 'history' ? <ChapterResultPanel detail={detail} onChanged={reload} /> : section === 'candidates' ? <CandidatePanel detail={detail} onChanged={reload} /> : section === 'packs' ? <AbilityPackPanel detail={detail} onChanged={reload} onOpenResults={() => setSection('drafts')} /> : ['canon'].includes(section) ? <CanonPanel detail={detail} characters={characters} onChanged={reload} view="facts" /> : body
  return <div className="flex h-full min-h-0 flex-col"><header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-workspace px-4"><button onClick={() => navigate(script ? '/?mode=script' : '/?mode=writing')} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm hover:bg-hover"><ArrowLeft className="size-4" />返回书架</button><div className="min-w-0 text-center"><p className="truncate text-sm font-semibold">{detail.title}</p><p className="text-[11px] text-muted-foreground">{script ? '剧本工作台' : '写作工作台'}</p></div><div className="flex items-center gap-1"><button onClick={() => setTaskOpen(true)} className="relative rounded-lg p-2 hover:bg-hover" title="后台任务"><ListTodo className="size-4" />{tasks.some((task) => ['queued', 'running', 'cancel_requested'].includes(task.status)) ? <span className="absolute right-1 top-1 size-1.5 rounded-full bg-brand" /> : null}</button><button onClick={() => void reload()} className="rounded-lg p-2 hover:bg-hover" title="刷新当前数据"><RefreshCw className="size-4" /></button></div></header><div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)]"><WorkbenchSidebar groups={groups} section={section} onSelect={setSection} /><main className="min-w-0 overflow-auto bg-background p-5">{error ? <p className="mb-4 rounded-xl border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}{workspaceBody}</main></div>{taskOpen ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"><div className="relative max-h-[80vh] w-full max-w-2xl overflow-auto"><button onClick={() => setTaskOpen(false)} className="absolute right-3 top-3 z-10 rounded-lg p-2 hover:bg-hover" title="关闭"><X className="size-4" /></button>{taskPanel}</div></div> : null}</div>
}

function AppRoutes() {
  const [authenticated, setAuthenticated] = useState(isLoggedIn())
  if (!authenticated) return <LoginScreen onLoggedIn={() => setAuthenticated(true)} />
  return <Routes><Route path="/" element={<LibraryPage onLogout={() => setAuthenticated(false)} />} /><Route path="/workbench" element={<WorkbenchPage />} /><Route path="/settings" element={<AccountSettingsPage onLogout={() => setAuthenticated(false)} />} /><Route path="*" element={<LibraryPage onLogout={() => setAuthenticated(false)} />} /></Routes>
}

export function App() { return <HashRouter><AppRoutes /></HashRouter> }
