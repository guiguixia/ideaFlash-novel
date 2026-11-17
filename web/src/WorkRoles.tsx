import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ImagePlus, RotateCcw, Send, Sparkles, Trash2, UserPlus } from "lucide-react";
import { kernelDelete, kernelGet, kernelPatch, kernelPost, kernelStreamPost, kernelUpload, kernelUrl } from "./lib/kernel-api";

type Role = { id: string; name: string; aliases: string[]; identity: string; personality: string; speechStyle: string; appearance: string; background: string; memoryChapter: number; imageUrl: string; hasChat: boolean; updatedAt?: string; chatUpdatedAt?: string };
type Segment = { sequence: number; title: string };
type Page = { items: Segment[]; totalPages: number };
type Chat = { id: string; userSetting: string; turn: number; updatedAt?: string; history: { role: "user" | "assistant"; content: string; status?: string }[] };
type Evidence = { sequence: number; title: string };
type Draft = Omit<Role, "id" | "imageUrl" | "hasChat">;

const empty: Draft = { name: "", aliases: [], identity: "", personality: "", speechStyle: "", appearance: "", background: "", memoryChapter: 0 };
const failure = (error: unknown) => error instanceof Error ? error.message : "操作失败，请重试";
const aliasesText = (aliases: string[]) => aliases.join("、");
const parseAliases = (value: string) => [...new Set(value.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean))];

export function WorkRoles({ workId, imported }: { workId: string; imported: boolean }) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selected, setSelected] = useState<Role | null>(null);
  const [creating, setCreating] = useState(false);
  const [createDialog, setCreateDialog] = useState(false);
  const [roleTab, setRoleTab] = useState<"create" | "chat">("create");
  const [chatDialog, setChatDialog] = useState(false);
  const [resetDialog, setResetDialog] = useState(false);
  const [deleteChatDialog, setDeleteChatDialog] = useState(false);
  const [chatRoleId, setChatRoleId] = useState("");
  const [userSetting, setUserSetting] = useState("");
  const [editingUserSetting, setEditingUserSetting] = useState(false);
  const [draft, setDraft] = useState<Draft>(empty);
  const [chat, setChat] = useState<Chat | null>(null);
  const [input, setInput] = useState("");
  const [aliasInput, setAliasInput] = useState("");
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    const items = await kernelGet<Role[]>(`/api/works/${workId}/roles`);
    setRoles(items);
    if (selected) setSelected(items.find((item) => item.id === selected.id) || null);
    return items;
  };

  useEffect(() => { void load().catch((reason) => setError(failure(reason))); }, [workId]);
  useEffect(() => {
    if (!imported) return;
    const fetchSegments = async () => {
      const first = await kernelGet<Page>(`/api/works/${workId}/segments?page=1&page_size=50`);
      let items = first.items;
      for (let page = 2; page <= first.totalPages; page += 1) items = items.concat((await kernelGet<Page>(`/api/works/${workId}/segments?page=${page}&page_size=50`)).items);
      setSegments(items);
    };
    void fetchSegments().catch((reason) => setError(failure(reason)));
  }, [workId, imported]);
  useEffect(() => {
    if (roleTab !== "chat" || !selected?.hasChat) return;
    void kernelGet<Chat>(`/api/works/${workId}/roles/${selected.id}/chat`).then(setChat).catch((reason) => setError(failure(reason)));
  }, [roleTab, selected?.id, selected?.hasChat, workId]);

  const beginCreate = () => {
    setRoleTab("create");
    setSelected(null);
    setCreating(false);
    setCreateDialog(true);
    setDraft({ ...empty, memoryChapter: imported ? segments.at(-1)?.sequence || 0 : 0 });
    setAliasInput("");
    setChat(null);
    setEvidence([]);
    setError("");
  };

  const switchRoleTab = (tab: "create" | "chat") => {
    if (tab === roleTab) return;
    const first = tab === "chat"
      ? [...roles].filter((role) => role.hasChat).sort((left, right) => (Date.parse(right.chatUpdatedAt || "") || 0) - (Date.parse(left.chatUpdatedAt || "") || 0))[0]
      : [...roles].sort((left, right) => (Date.parse(right.updatedAt || "") || 0) - (Date.parse(left.updatedAt || "") || 0))[0];
    setRoleTab(tab);
    setSelected(null);
    setCreating(false);
    setDraft(empty);
    setAliasInput("");
    setEvidence([]);
    setChat(null);
    setInput("");
    setEditingUserSetting(false);
    setError("");
    if (first) void select(first, tab);
  };

  const select = async (role: Role, tab = roleTab) => {
    setSelected(role);
    setCreating(false);
    setDraft({ name: role.name, aliases: role.aliases || [], identity: role.identity, personality: role.personality, speechStyle: role.speechStyle, appearance: role.appearance, background: role.background, memoryChapter: role.memoryChapter });
    setAliasInput(aliasesText(role.aliases || []));
    setEvidence([]);
    setChat(tab === "chat" && role.hasChat ? await kernelGet<Chat>(`/api/works/${workId}/roles/${role.id}/chat`) : null);
  };

  useEffect(() => {
    if (roleTab !== "create" || selected || creating || createDialog || roles.length === 0) return;
    const first = [...roles].sort((left, right) => (Date.parse(right.updatedAt || "") || 0) - (Date.parse(left.updatedAt || "") || 0))[0];
    if (first) void select(first, "create");
  }, [roleTab, selected?.id, creating, createDialog, roles]);

  useLayoutEffect(() => {
    if (roleTab !== "chat" || !chat) return;
    const scrollToLatest = () => {
      const history = chatHistoryRef.current;
      if (history) history.scrollTo({ top: history.scrollHeight, behavior: "auto" });
    };
    scrollToLatest();
    const frame = window.requestAnimationFrame(scrollToLatest);
    const timer = window.setTimeout(scrollToLatest, 80);
    return () => { window.cancelAnimationFrame(frame); window.clearTimeout(timer); };
  }, [roleTab, chat?.id, chat?.history.length, chat?.history.at(-1)?.content]);

  const extract = async () => {
    if (!draft.name.trim() || !draft.memoryChapter) return;
    try {
      setBusy(true);
      const result = await kernelPost<Draft & { evidence: Evidence[] }>(`/api/works/${workId}/roles/extract`, { name: draft.name.trim(), aliases: parseAliases(aliasInput), memory_chapter: draft.memoryChapter });
      setDraft((current) => ({ ...current, aliases: result.aliases, background: result.background, appearance: result.appearance, personality: result.personality, speechStyle: result.speechStyle }));
      setAliasInput(aliasesText(result.aliases));
      setEvidence(result.evidence);
      setCreating(true);
      setCreateDialog(false);
      setError("");
    } catch (reason) {
      setError(failure(reason));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    try {
      setBusy(true);
      const payload = { ...draft, aliases: parseAliases(aliasInput), memory_chapter: Number(draft.memoryChapter), speech_style: draft.speechStyle };
      const role = selected
        ? await kernelPatch<Role>(`/api/works/${workId}/roles/${selected.id}`, payload)
        : await kernelPost<Role>(`/api/works/${workId}/roles`, payload);
      const items = await load();
      await select(items.find((item) => item.id === role.id) || role);
      setError("");
    } catch (reason) {
      setError(failure(reason));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File) => {
    if (!selected) return;
    try {
      const form = new FormData();
      form.append("file", file);
      const role = await kernelUpload<Role>(`/api/works/${workId}/roles/${selected.id}/image`, form);
      await load();
      setSelected(role);
    } catch (reason) { setError(failure(reason)); }
  };

  const openPet = () => {
    if (!selected?.imageUrl) {
      setError("请先上传角色参考图，再生成桌宠。");
      return;
    }
    const url = new URL("desktop-pet/pet.html", window.location.href);
    url.searchParams.set("name", selected.name);
    url.searchParams.set("image", kernelUrl(selected.imageUrl));
    window.open(url.toString(), `role-pet-${selected.id}`, "width=350,height=520");
  };

  const reset = async () => {
    if (!selected || !chat) return;
    try {
      setBusy(true);
      if (userSetting !== chat.userSetting) await kernelPatch<Chat>(`/api/works/${workId}/roles/${selected.id}/chat`, { user_setting: userSetting });
      const next = await kernelPost<Chat>(`/api/works/${workId}/roles/${selected.id}/chat/reset`, {});
      setChat(next);
      setRoles((current) => current.map((role) => role.id === selected.id ? { ...role, chatUpdatedAt: next.updatedAt } : role));
      setEditingUserSetting(false);
      setResetDialog(false);
    } catch (reason) { setError(failure(reason)); } finally { setBusy(false); }
  };

  const deleteChat = async () => {
    if (!selected || !chat) return;
    try {
      setBusy(true);
      await kernelDelete(`/api/works/${workId}/roles/${selected.id}/chat`);
      setRoles((current) => current.map((role) => role.id === selected.id ? { ...role, hasChat: false, chatUpdatedAt: undefined } : role));
      setSelected(null);
      setDraft(empty);
      setChat(null);
      setInput("");
      setUserSetting("");
      setEditingUserSetting(false);
      setDeleteChatDialog(false);
      setError("");
    } catch (reason) { setError(failure(reason)); } finally { setBusy(false); }
  };

  const createChat = async () => {
    if (!chatRoleId) return;
    try {
      setBusy(true);
      const next = await kernelPost<Chat>(`/api/works/${workId}/roles/${chatRoleId}/chat`, { user_setting: userSetting });
      const role = roles.find((item) => item.id === chatRoleId);
      if (role) { setSelected({ ...role, hasChat: true, chatUpdatedAt: next.updatedAt }); setDraft({ name: role.name, aliases: role.aliases || [], identity: role.identity, personality: role.personality, speechStyle: role.speechStyle, appearance: role.appearance, background: role.background, memoryChapter: role.memoryChapter }); }
      setChat(next); setChatDialog(false); setUserSetting(""); await load();
    } catch (reason) { setError(failure(reason)); } finally { setBusy(false); }
  };

  const saveUserSetting = async () => {
    if (!selected || !chat) return;
    try {
      setBusy(true);
      const next = await kernelPatch<Chat>(`/api/works/${workId}/roles/${selected.id}/chat`, { user_setting: userSetting });
      setChat(next);
      setRoles((current) => current.map((role) => role.id === selected.id ? { ...role, chatUpdatedAt: next.updatedAt } : role));
      setEditingUserSetting(false);
    } catch (reason) { setError(failure(reason)); } finally { setBusy(false); }
  };

  const send = async () => {
    if (!selected || !chat || !input.trim()) return;
    const message = input.trim();
    setInput("");
    setBusy(true);
    setChat((current) => current ? { ...current, history: [...current.history, { role: "user", content: message }, { role: "assistant", content: "", status: "generating" }] } : current);
    try {
      const result = await kernelStreamPost<Chat>(`/api/works/${workId}/roles/${selected.id}/chat/turn`, { message }, (chunk) => setChat((current) => current ? { ...current, history: current.history.map((item, index, rows) => index === rows.length - 1 ? { ...item, content: item.content + chunk } : item) } : current));
      setChat(result);
      setRoles((current) => current.map((role) => role.id === selected.id ? { ...role, chatUpdatedAt: result.updatedAt } : role));
    } catch (reason) {
      setError(failure(reason));
      setChat((current) => current ? { ...current, history: current.history.slice(0, -2) } : current);
      setInput(message);
    } finally { setBusy(false); }
  };

  const editing = roleTab === "create" ? creating || !!selected : !!(selected && chat);
  const byUpdatedAt = (left: Role, right: Role, field: "updatedAt" | "chatUpdatedAt") => (Date.parse(right[field] || "") || 0) - (Date.parse(left[field] || "") || 0);
  const listedRoles = roleTab === "chat"
    ? roles.filter((role) => role.hasChat).sort((left, right) => byUpdatedAt(left, right, "chatUpdatedAt"))
    : [...roles].sort((left, right) => byUpdatedAt(left, right, "updatedAt"));
  return (
    <section className="space-y-5">
      <nav className="flex flex-wrap gap-2" aria-label="角色功能">
        <button type="button" onClick={() => switchRoleTab("create")} className={`rounded-lg border px-4 py-2 text-sm transition-colors ${roleTab === "create" ? "border-brand-border bg-brand-soft font-semibold text-brand" : "border-border bg-workspace text-muted-foreground hover:bg-hover"}`}>新增角色</button>
        <button type="button" onClick={() => switchRoleTab("chat")} className={`rounded-lg border px-4 py-2 text-sm transition-colors ${roleTab === "chat" ? "border-brand-border bg-brand-soft font-semibold text-brand" : "border-border bg-workspace text-muted-foreground hover:bg-hover"}`}>角色聊天</button>
      </nav>
      <div className="grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)]">
      <aside className="rounded-[18px] border bg-workspace p-4">
        <button onClick={roleTab === "create" ? beginCreate : () => { setChatRoleId(""); setUserSetting(""); setChatDialog(true); }} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-brand-border bg-brand-soft px-3 py-2 text-sm font-medium text-brand"><UserPlus className="size-4" />{roleTab === "create" ? "新建角色卡" : "新建会话"}</button>
        <div className="mt-3 space-y-2">
          {listedRoles.map((role) => <button key={role.id} onClick={() => void select(role)} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left text-sm ${selected?.id === role.id ? "border-brand-border bg-brand-soft" : "border-border bg-workspace/40 hover:bg-hover"}`}>{role.imageUrl ? <img src={kernelUrl(role.imageUrl)} alt="" className="size-11 rounded-lg object-cover" /> : <span className="grid size-11 place-items-center rounded-lg bg-brand-soft text-brand">{role.name.slice(0, 1)}</span>}<span className="min-w-0"><span className="block truncate font-medium">{role.name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{role.aliases.length ? `别名：${aliasesText(role.aliases)}` : "作品设定"}</span></span></button>)}
          {listedRoles.length === 0 && <p className="rounded-xl border border-dashed border-border px-3 py-5 text-center text-xs leading-5 text-muted-foreground">{roleTab === "create" ? "还没有角色卡。先创建角色，再让系统从原文中提炼角色资料。" : "还没有角色会话。点击“新建会话”开始聊天。"}</p>}
        </div>
      </aside>

      <main className="rounded-[18px] border bg-workspace p-5">
        {!editing ? <div className="grid min-h-80 place-items-center text-center"><div><p className="text-sm text-muted-foreground">{roleTab === "create" ? "创建作品级角色卡，选择记忆边界后从原文提炼背景与外貌。" : roles.length === 0 ? "先创建角色卡，再在这里开启角色的唯一会话。" : "选择一个角色，设置聊天设定后开始会话。"}</p>{roleTab === "create" ? <button onClick={beginCreate} className="mt-4 rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">创建角色卡</button> : roles.length === 0 ? <button onClick={() => switchRoleTab("create")} className="mt-4 rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">前往新增角色</button> : <button onClick={() => { setChatRoleId(""); setUserSetting(""); setChatDialog(true); }} className="mt-4 rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground">新建会话</button>}</div></div> : <>
          <header className={roleTab === "create" ? "flex items-start justify-between gap-3" : "hidden"}><div><p className="text-xs font-semibold text-brand">作品级角色卡</p><h2 className="mt-1 text-xl font-semibold">{draft.name}</h2><p className="mt-1 text-sm text-muted-foreground">{draft.aliases.length ? `别名：${aliasesText(draft.aliases)}${draft.memoryChapter ? " · " : ""}` : ""}{draft.memoryChapter ? `记忆截至第 ${draft.memoryChapter} 章` : (draft.aliases.length ? "" : "作品设定")}</p></div><button disabled={busy || !draft.name.trim() || (creating && evidence.length === 0)} onClick={() => void save()} className="rounded-lg bg-foreground px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">保存角色卡</button></header>
          {roleTab === "create" && evidence.length > 0 && <p className="mt-4 rounded-lg border border-brand-border bg-brand-soft px-3 py-2 text-xs text-muted-foreground">提取依据：{evidence.map((item) => `第 ${item.sequence} 章${item.title ? `《${item.title}》` : ""}`).join("、")}</p>}

          <div className={roleTab === "create" ? "mt-5 grid gap-3 sm:grid-cols-2" : "hidden"}>
            {(["background", "appearance"] as const).map((key) => <label key={key} className="text-sm">{key === "background" ? "背景" : "外貌"}<textarea value={draft[key]} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} rows={4} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label>)}
          </div>
          {roleTab === "create" && imported && <label className="mt-4 block max-w-md text-sm">记忆截至章节<select value={draft.memoryChapter} onChange={(event) => setDraft({ ...draft, memoryChapter: Number(event.target.value) })} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2"><option value={0}>请选择章节</option>{segments.map((segment) => <option key={segment.sequence} value={segment.sequence}>第 {segment.sequence} 章结束 · {segment.title}</option>)}</select></label>}

          {selected && <div className={roleTab === "create" ? "mt-5 flex items-center gap-3 border-t pt-5" : "hidden"}>{selected.imageUrl ? <img src={kernelUrl(selected.imageUrl)} alt={selected.name} className="size-16 rounded-xl object-cover" /> : <div className="grid size-16 place-items-center rounded-xl bg-brand-soft text-brand"><ImagePlus /></div>}<button onClick={() => fileRef.current?.click()} className="rounded-lg border px-3 py-2 text-sm">上传参考图</button><button type="button" onClick={openPet} className="inline-flex items-center gap-2 rounded-lg border border-brand-border bg-brand-soft px-3 py-2 text-sm font-medium text-brand"><Sparkles className="size-4" />生成桌宠</button><input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (file) void upload(file); }} /></div>}

          <div className={roleTab === "chat" ? "mt-1 border-t pt-5" : "hidden"}><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-brand">唯一会话</p><h3 className="mt-1 font-semibold">当前与 {selected?.name || draft.name} 聊天</h3>{chat && (editingUserSetting ? <div className="mt-2 flex gap-2"><input value={userSetting} onChange={(event) => setUserSetting(event.target.value)} placeholder="例如：故人" className="min-w-0 rounded-lg border bg-surface px-3 py-1.5 text-sm"/><button type="button" disabled={busy} onClick={() => void saveUserSetting()} className="rounded-lg bg-foreground px-3 py-1.5 text-sm text-primary-foreground">保存</button></div> : <p className="mt-1 text-sm text-muted-foreground">用户设定：{chat.userSetting || "未设置"} <button type="button" onClick={() => { setUserSetting(chat.userSetting); setEditingUserSetting(true); }} className="ml-1 text-brand hover:underline">修改</button></p>)}</div>{selected && chat && <div className="flex gap-2"><button onClick={() => { setUserSetting(chat.userSetting); setResetDialog(true); }} className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-sm text-destructive"><RotateCcw className="size-4" />重置</button><button onClick={() => setDeleteChatDialog(true)} className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-sm text-destructive"><Trash2 className="size-4" />删除会话</button></div>}</div>{selected && chat ? <><div ref={chatHistoryRef} className="mt-4 max-h-80 space-y-2 overflow-auto">{chat.history.length ? chat.history.map((row, index) => <p key={index} className={`rounded-lg p-3 text-sm leading-6 ${row.role === "user" ? "ml-10 bg-foreground text-primary-foreground" : "mr-10 bg-active"}`}>{row.content || "正在回复…"}</p>) : null}</div><div className="mt-3 flex gap-2"><input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void send(); }} placeholder="说点什么…" className="min-w-0 flex-1 rounded-lg border bg-surface px-3 py-2 text-sm"/><button disabled={busy || !input.trim()} onClick={() => void send()} className="rounded-lg bg-foreground px-3 text-primary-foreground"><Send className="size-4" /></button></div></> : <p className="mt-4 text-sm text-muted-foreground">选择已有会话，或点击“新建会话”开始聊天。</p>}</div>
        </>}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </main>
      {createDialog && <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" role="presentation" onMouseDown={() => setCreateDialog(false)}><section role="dialog" aria-modal="true" aria-labelledby="create-role-title" className="w-full max-w-lg rounded-2xl border border-border bg-workspace p-5 shadow-xl" onMouseDown={(event) => event.stopPropagation()}><header className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold text-brand">新建角色卡</p><h2 id="create-role-title" className="mt-1 text-xl font-semibold">设置原文提取条件</h2><p className="mt-1 text-sm text-muted-foreground">背景与外貌会由原文提取生成，无需预先填写。</p></div><button type="button" onClick={() => setCreateDialog(false)} className="rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-active">关闭</button></header><div className="mt-5 space-y-3"><label className="block text-sm">名称<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} maxLength={80} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label><label className="block text-sm">别名<input value={aliasInput} onChange={(event) => setAliasInput(event.target.value)} placeholder="中英文逗号或顿号均可分隔" className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label>{imported && <label className="block text-sm">记忆截至章节<select value={draft.memoryChapter} onChange={(event) => setDraft({ ...draft, memoryChapter: Number(event.target.value) })} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2"><option value={0}>请选择章节</option>{segments.map((segment) => <option key={segment.sequence} value={segment.sequence}>第 {segment.sequence} 章结束 · {segment.title}</option>)}</select></label>}</div><footer className="mt-5 flex justify-end"><button type="button" disabled={busy || !draft.name.trim() || (imported && !draft.memoryChapter)} onClick={() => void extract()} className="inline-flex items-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-foreground disabled:opacity-50"><Sparkles className="size-4" />从原文抽取</button></footer></section></div>}
      {chatDialog && <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" role="presentation" onMouseDown={() => setChatDialog(false)}><section role="dialog" aria-modal="true" aria-labelledby="create-chat-title" className="w-full max-w-lg rounded-2xl border border-border bg-workspace p-5 shadow-xl" onMouseDown={(event) => event.stopPropagation()}><header><p className="text-xs font-semibold text-brand">新建会话</p><h2 id="create-chat-title" className="mt-1 text-xl font-semibold">选择角色与聊天设定</h2></header><div className="mt-5 space-y-3"><label className="block text-sm">角色<select value={chatRoleId} onChange={(event) => setChatRoleId(event.target.value)} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2"><option value="">请选择尚未建立会话的角色</option>{roles.filter((role) => !role.hasChat).map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label><label className="block text-sm">用户设定<textarea value={userSetting} onChange={(event) => setUserSetting(event.target.value)} placeholder="例如：陌生人、故人、师徒或旧友" rows={3} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label></div><footer className="mt-5 flex justify-end"><button type="button" disabled={busy || !chatRoleId} onClick={() => void createChat()} className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-foreground disabled:opacity-50">创建唯一会话</button></footer></section></div>}
      {deleteChatDialog && <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" role="presentation" onMouseDown={() => setDeleteChatDialog(false)}><section role="dialog" aria-modal="true" aria-labelledby="delete-chat-title" className="w-full max-w-lg rounded-2xl border border-border bg-workspace p-5 shadow-xl" onMouseDown={(event) => event.stopPropagation()}><header><p className="text-xs font-semibold text-destructive">删除会话</p><h2 id="delete-chat-title" className="mt-1 text-xl font-semibold">删除与 {selected?.name} 的会话？</h2></header><p className="mt-3 text-sm text-muted-foreground">聊天记录与长期记忆将被永久删除，角色卡会保留。</p><footer className="mt-6 flex items-center justify-end gap-3 border-t border-border pt-4"><button type="button" onClick={() => setDeleteChatDialog(false)} className="min-w-20 rounded-lg border border-border bg-workspace px-4 py-2.5 text-sm font-medium">取消</button><button type="button" disabled={busy} onClick={() => void deleteChat()} className="min-w-28 rounded-lg bg-[#c83b2a] px-4 py-2.5 text-sm font-semibold text-white shadow-sm disabled:opacity-50">确认删除会话</button></footer></section></div>}
      {resetDialog && <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" role="presentation" onMouseDown={() => setResetDialog(false)}><section role="dialog" aria-modal="true" aria-labelledby="reset-chat-title" className="w-full max-w-lg rounded-2xl border border-border bg-workspace p-5 shadow-xl" onMouseDown={(event) => event.stopPropagation()}><header><p className="text-xs font-semibold text-destructive">重置唯一会话</p><h2 id="reset-chat-title" className="mt-1 text-xl font-semibold">清空聊天记录与长期记忆</h2></header><p className="mt-3 text-sm text-muted-foreground">你可以同时修改最新的用户设定；确认后将无法恢复当前会话内容。</p><label className="mt-4 block text-sm">用户设定<textarea value={userSetting} onChange={(event) => setUserSetting(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border bg-surface px-3 py-2" /></label><footer className="mt-5 flex justify-end gap-2 border-t border-border pt-4"><button type="button" onClick={() => setResetDialog(false)} className="rounded-lg border px-4 py-2 text-sm">取消</button><button type="button" disabled={busy} onClick={() => void reset()} className="rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">确认重置</button></footer></section></div>}
      </div>
    </section>
  );
}
