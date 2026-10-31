import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import {
  BookOpen,
  BriefcaseBusiness,
  Clapperboard,
  GraduationCap,
  Library,
  LockKeyhole,
  Mountain,
  Plus,
  Settings,
  Sparkles,
  Swords,
  X,
} from "lucide-react";
import {
  kernelDelete,
  kernelGet,
  kernelPost,
  kernelUpload,
} from "./lib/kernel-api";

type Kind = "original_story" | "imported_novel" | "imported_screenwork";
type Work = {
  id: string;
  title: string;
  workType: Kind;
  summary: string;
  sourceSegmentCount: number;
  scriptCount: number;
};
type StoryDraft = {
  title: string;
  summary: string;
  genre: string;
  world: string;
  playerIdentity: string;
  openingScene: string;
  tone: string;
};
type TemplateId =
  | "blank"
  | "spring-recruiting"
  | "last-escort"
  | "outer-disciple"
  | "cloud-city";
type StoryTemplate = {
  id: Exclude<TemplateId, "blank">;
  title: string;
  subtitle: string;
  summary: string;
  icon: typeof Sparkles;
  draft: StoryDraft;
};

const labels: Record<Kind, string> = {
  original_story: "原创故事",
  imported_novel: "导入小说",
  imported_screenwork: "导入影视资料",
};
const failure = (e: unknown) =>
  e instanceof Error ? e.message : "操作失败，请重试";
const blankDraft: StoryDraft = {
  title: "",
  summary: "",
  genre: "",
  world: "",
  playerIdentity: "",
  openingScene: "",
  tone: "",
};
const templates: StoryTemplate[] = [
  {
    id: "spring-recruiting",
    title: "春招倒计时",
    subtitle: "都市成长",
    icon: GraduationCap,
    summary: "签约截止前七天，你要决定去哪里，也要决定成为谁。",
    draft: {
      title: "春招倒计时",
      summary:
        "签约截止前七天，一名应届毕业生在理想、现实与关系之间做出第一份人生选择。",
      genre: "都市现实 · 成长",
      world:
        "春招季的云城，机会与焦虑同时涌进校园。大厂 offer、初创团队、家乡岗位与未知的自由职业，都在等待一个答案。",
      playerIdentity:
        "即将毕业的大学生，手握一份保底 offer，却还没决定要不要签下它。",
      openingScene:
        "上午九点，你收到理想公司的终面通知；同一刻，保底 offer 的签约倒计时只剩七天。",
      tone: "现实、克制、带一点青春的锋利",
    },
  },
  {
    id: "last-escort",
    title: "镖局最后一趟镖",
    subtitle: "武侠江湖",
    icon: Swords,
    summary: "这次押的不是货，而是一个所有人都在找的人。",
    draft: {
      title: "镖局最后一趟镖",
      summary:
        "老镖局关门前的最后一单，你护送的神秘客人牵出一桩旧案，也把你推回江湖中心。",
      genre: "传统武侠 · 江湖抉择",
      world:
        "大晟末年，江湖门派、地方豪强与朝廷暗线彼此纠缠。镖局看似只走银钱货物，实则替无数人走过不能见光的路。",
      playerIdentity: "刚出师不久的年轻镖师，也是镖局总镖头最不放心的徒弟。",
      openingScene:
        "大雨压城，镖局最后一盏灯还亮着。总镖头把一枚染血的木牌与一封密信交到你手里。",
      tone: "苍凉、热血、重承诺与人情",
    },
  },
  {
    id: "outer-disciple",
    title: "山门外门三年",
    subtitle: "仙侠修行",
    icon: Mountain,
    summary: "宗门大比前七日，你得到一次改写灵根的机会。",
    draft: {
      title: "山门外门三年",
      summary:
        "灵根平平的外门弟子在晋升无望之际，得到一桩可能改变命运、也可能毁掉道途的机缘。",
      genre: "仙侠 · 修行成长",
      world:
        "太微山门立于群峰云海之间，外门弟子争资源、争师承、争一次进入秘境的资格；山外妖患渐起，旧日禁地也开始苏醒。",
      playerIdentity:
        "入门三年、修为停滞的外门弟子，离被逐下山只差最后一次大比。",
      openingScene:
        "夜巡禁地时，你在枯井深处发现一枚仍在跳动的灵石；宗门大比还有七天。",
      tone: "清峻、热血、机缘与代价并存",
    },
  },
  {
    id: "cloud-city",
    title: "云城合伙人",
    subtitle: "事业人生",
    icon: BriefcaseBusiness,
    summary: "融资签约当天，合伙人要走，还要带走最重要的客户。",
    draft: {
      title: "云城合伙人",
      summary:
        "事业刚进入上升期的创业公司合伙人，在融资、用人、亲密关系与原则之间，重新定义何为成功。",
      genre: "都市商业 · 人生选择",
      world:
        "云城是高速增长的新一线城市。资本、人才与舆论追逐每一个新故事；你的公司刚走到聚光灯下，也第一次真正暴露在风险里。",
      playerIdentity:
        "一家科技创业公司的创始合伙人，负责业务与产品，习惯把一切都扛在自己身上。",
      openingScene:
        "融资签约会开始前两小时，核心合伙人提出离开，并带走了最大的客户名单。",
      tone: "冷静、紧迫、兼顾野心与关系",
    },
  },
];
const templateById = new Map(
  templates.map((template) => [template.id, template]),
);
const createOptions: [Kind, string, string, typeof Sparkles, boolean?][] = [
  ["original_story", "创建原创故事", "从人生模板或空白世界开始", Sparkles],
  ["imported_novel", "导入小说", "选择连续章节，生成私有体验副本", BookOpen],
  [
    "imported_screenwork",
    "导入影视资料",
    "即将支持导入剧本、字幕或梗概",
    Clapperboard,
    true,
  ],
];
const sameDraft = (left: StoryDraft, right: StoryDraft) =>
  Object.keys(left).every(
    (key) => left[key as keyof StoryDraft] === right[key as keyof StoryDraft],
  );

export function LibraryHome() {
  const nav = useNavigate();
  const [works, setWorks] = useState<Work[]>([]),
    [open, setOpen] = useState(false),
    [kind, setKind] = useState<Kind>("original_story"),
    [draft, setDraft] = useState<StoryDraft>(blankDraft),
    [templateId, setTemplateId] = useState<TemplateId>("blank"),
    [pendingTemplate, setPendingTemplate] = useState<TemplateId | null>(null),
    [showDetails, setShowDetails] = useState(false),
    [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [deletingId, setDeletingId] = useState<string | null>(null),
    [error, setError] = useState("");
  const load = () =>
    kernelGet<Work[]>("/api/works")
      .then(setWorks)
      .catch((e) => setError(failure(e)));
  const baseline = useMemo(
    () =>
      templateId === "blank"
        ? blankDraft
        : templateById.get(templateId)?.draft || blankDraft,
    [templateId],
  );
  const hasUnsavedStoryChanges = !sameDraft(draft, baseline);
  useEffect(() => {
    void load();
  }, []);
  function begin(next: Kind = "original_story") {
    if (next === "imported_screenwork") return;
    setKind(next);
    setDraft(blankDraft);
    setTemplateId("blank");
    setPendingTemplate(null);
    setShowDetails(false);
    setFile(null);
    setError("");
    setOpen(true);
  }
  function setField(field: keyof StoryDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }
  function applyTemplate(next: TemplateId) {
    setDraft({
      ...((next === "blank" ? undefined : templateById.get(next))?.draft ||
        blankDraft),
    });
    setTemplateId(next);
    setPendingTemplate(null);
  }
  function selectTemplate(next: TemplateId) {
    if (next === templateId) return;
    if (hasUnsavedStoryChanges) {
      setPendingTemplate(next);
      return;
    }
    applyTemplate(next);
  }
  function selectKind(next: Kind) {
    if (next === "imported_screenwork") return;
    setKind(next);
    setFile(null);
    setError("");
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let work: Work;
      if (kind === "original_story") {
        work = await kernelPost<Work>("/api/works", {
          title: draft.title,
          summary: draft.summary,
          genre: draft.genre,
          world: draft.world,
          player_identity: draft.playerIdentity,
          opening_scene: draft.openingScene,
          tone: draft.tone,
        });
        const script = await kernelPost<{ id: string }>(
          `/api/works/${work.id}/scripts`,
          {
            title: "开局体验",
            start_sequence: 0,
            end_sequence: 0,
            player_identity: draft.playerIdentity,
            perspective: "first",
          },
        );
        setOpen(false);
        nav(`/workbench?id=${work.id}&tab=experience&script=${script.id}`);
        return;
      } else {
        if (!file) throw new Error("请选择要导入的文本文件");
        const form = new FormData();
        form.append("work_type", kind);
        form.append("title", draft.title);
        form.append("file", file);
        work = await kernelUpload<Work>("/api/works/import", form);
      }
      setOpen(false);
      nav(`/workbench?id=${work.id}`);
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  async function removeWork(work: Work) {
    if (
      !window.confirm(
        `确定删除「${work.title}」吗？其资料、副本和体验记录也会一并删除。`,
      )
    )
      return;
    setDeletingId(work.id);
    setError("");
    try {
      await kernelDelete(`/api/works/${work.id}`);
      setWorks((current) => current.filter((item) => item.id !== work.id));
    } catch (e) {
      setError(failure(e));
    } finally {
      setDeletingId(null);
    }
  }
  const field = (
    name: keyof StoryDraft,
    label: string,
    large = false,
    placeholder = "",
  ) => (
    <label className="block text-sm font-medium">
      {label}
      {large ? (
        <textarea
          value={draft[name]}
          onChange={(event) => setField(name, event.target.value)}
          placeholder={placeholder}
          className="mt-1.5 min-h-24 w-full rounded-lg border bg-surface p-3 leading-6"
        />
      ) : (
        <input
          required={name === "title"}
          value={draft[name]}
          onChange={(event) => setField(name, event.target.value)}
          placeholder={placeholder}
          className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5"
        />
      )}
    </label>
  );
  const storyTemplates = [
    {
      id: "blank" as const,
      title: "从空白故事开始",
      subtitle: "完全由你定义",
      summary: "不预填任何设定，直接建立自己的世界。",
      icon: Sparkles,
    },
    ...templates,
  ];

  return (
    <main className="min-h-screen bg-background">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <button
          onClick={() => nav("/")}
          className="flex items-center gap-2 font-semibold"
        >
          <Library className="size-5 text-brand" />
          我的作品
        </button>
        <button
          type="button"
          onClick={() => nav("/settings")}
          className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-hover"
        >
          <Settings className="size-4" />
          设置
        </button>
      </header>
      <div className="mx-auto max-w-6xl px-6 pb-12">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm text-brand">私有故事实验室</p>
            <h1 className="mt-1 text-3xl font-semibold">
              进入、改造、体验你的故事
            </h1>
          </div>
          <button
            onClick={() => begin()}
            className="inline-flex items-center gap-2 rounded-lg bg-foreground px-4 py-2.5 text-sm font-medium text-primary-foreground"
          >
            <Plus className="size-4" />
            新建作品
          </button>
        </div>
        {works.length ? (
          <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {works.map((work) => (
              <article
                key={work.id}
                className="group relative rounded-[18px] border border-border bg-workspace p-5 transition hover:-translate-y-0.5 hover:shadow-sm"
              >
                <button
                  type="button"
                  onClick={() => nav(`/workbench?id=${work.id}`)}
                  className="block w-full text-left"
                >
                  <div className="flex items-center justify-between pr-8">
                    <span className="rounded-full bg-active px-2.5 py-1 text-xs">
                      {labels[work.workType]}
                    </span>
                    <LockKeyhole className="size-4 text-muted-foreground" />
                  </div>
                  <h2 className="mt-5 text-lg font-semibold">{work.title}</h2>
                  <p className="mt-2 min-h-10 text-sm leading-5 text-muted-foreground">
                    {work.summary || "仅自己可体验的作品。"}
                  </p>
                  <p className="mt-5 text-xs text-muted-foreground">
                    {work.workType === "original_story"
                      ? `${work.scriptCount} 个体验版本`
                      : `${work.sourceSegmentCount} 个资料片段 · ${work.scriptCount} 个副本`}
                  </p>
                </button>
                <button
                  type="button"
                  aria-label={`删除作品 ${work.title}`}
                  title="删除作品"
                  disabled={deletingId === work.id}
                  onClick={() => void removeWork(work)}
                  className="absolute right-3 top-3 rounded-full p-1.5 text-destructive opacity-70 transition hover:bg-destructive hover:text-destructive-foreground hover:opacity-100 disabled:cursor-wait disabled:opacity-50"
                >
                  <X className="size-4" />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <section className="relative mx-auto mt-16 max-w-3xl overflow-hidden rounded-[26px] border border-border bg-workspace px-8 py-12 text-center shadow-[var(--shadow-workspace)]">
            <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-brand-soft to-transparent" />
            <Sparkles className="relative mx-auto size-8 text-brand" />
            <p className="relative mt-5 text-xl font-semibold">从一扇门开始</p>
            <p className="relative mx-auto mt-3 max-w-md text-sm leading-6 text-muted-foreground">
              选一个人生起点，或导入一段想重新进入的故事。所有作品和体验均仅自己可见。
            </p>
            <div className="relative mt-8 grid gap-3 text-left sm:grid-cols-3">
              {createOptions.map(
                ([value, name, description, Icon, disabled]) => (
                  <button
                    key={value}
                    disabled={disabled}
                    onClick={() => begin(value)}
                    className={`rounded-xl border border-border bg-surface p-4 ${disabled ? "cursor-not-allowed opacity-45" : "hover:border-brand-border hover:bg-brand-soft"}`}
                  >
                    <Icon className="size-4 text-brand" />
                    <p className="mt-4 text-sm font-medium">{name}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {description}
                    </p>
                  </button>
                ),
              )}
            </div>
          </section>
        )}
        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      </div>
      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/35 p-4"
          onMouseDown={() => !busy && setOpen(false)}
        >
          <form
            onSubmit={submit}
            onMouseDown={(event) => event.stopPropagation()}
            className="max-h-[calc(100vh-2rem)] w-full max-w-3xl overflow-y-auto rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium text-brand">新建作品</p>
                <h2 className="mt-1 text-2xl font-semibold">从哪里开始？</h2>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg px-2 py-1 text-sm hover:bg-hover"
              >
                关闭
              </button>
            </div>
            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {createOptions.map(
                ([value, name, description, Icon, disabled]) => (
                  <button
                    type="button"
                    disabled={disabled}
                    key={value}
                    onClick={() => selectKind(value)}
                    className={`rounded-xl border p-4 text-left ${disabled ? "cursor-not-allowed opacity-45" : kind === value ? "border-brand-border bg-brand-soft" : "border-border hover:bg-hover"}`}
                  >
                    <Icon className="size-4 text-brand" />
                    <p className="mt-3 text-sm font-medium">{name}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {description}
                    </p>
                  </button>
                ),
              )}
            </div>
            {kind === "original_story" ? (
              <>
                <div className="mt-6 flex items-end justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">选择一个人生起点</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      模板已包含完整设定；创建后随时可以继续改。
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full bg-brand-soft px-2.5 py-1 text-xs text-brand">
                    可编辑
                  </span>
                </div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {storyTemplates.map((template) => {
                    const Icon = template.icon;
                    const selected = templateId === template.id;
                    return (
                      <button
                        type="button"
                        key={template.id}
                        onClick={() => selectTemplate(template.id)}
                        className={`group relative overflow-hidden rounded-xl border p-4 text-left transition ${selected ? "border-brand-border bg-brand-soft shadow-sm" : "border-border bg-surface hover:border-brand-border hover:bg-hover"}`}
                      >
                        <Icon
                          className={`size-4 ${selected ? "text-brand" : "text-muted-foreground group-hover:text-brand"}`}
                        />
                        <p className="mt-5 text-base font-semibold">
                          {template.title}
                        </p>
                        <p className="mt-1 text-xs font-medium text-brand">
                          {template.subtitle}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          {template.summary}
                        </p>
                        {selected && (
                          <span className="absolute right-3 top-3 rounded-full bg-brand px-2 py-0.5 text-[11px] text-primary-foreground">
                            已选择
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-6 border-t border-border pt-5">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">给故事起个名字</p>
                    <button
                      type="button"
                      onClick={() => setShowDetails((value) => !value)}
                      className="text-xs text-brand"
                    >
                      {showDetails ? "收起详细设定" : "完善详细设定（可选）"}
                    </button>
                  </div>
                  <div className="mt-4">
                    {field("title", "故事名称", false, "例如：江湖夜雨")}
                  </div>
                  <div className="mt-4">
                    {field(
                      "summary",
                      "一句话简介",
                      true,
                      "这个故事从哪里开始？",
                    )}
                  </div>
                  {showDetails && (
                    <div className="mt-4 space-y-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        {field("genre", "题材", false, "例如：武侠、都市")}
                        {field("tone", "叙事基调", false, "例如：热血、克制")}
                      </div>
                      {field(
                        "world",
                        "世界观与规则",
                        true,
                        "这个世界有什么重要规则？",
                      )}
                      <div className="grid gap-4 sm:grid-cols-2">
                        {field(
                          "playerIdentity",
                          "玩家身份",
                          false,
                          "玩家会以谁的身份进入？",
                        )}
                        {field(
                          "openingScene",
                          "开局场景",
                          false,
                          "玩家会以谁的身份进入？",
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <>
                <label className="mt-5 block text-sm font-medium">
                  作品名称
                  <input
                    required
                    autoFocus
                    value={draft.title}
                    onChange={(event) => setField("title", event.target.value)}
                    className="mt-1.5 w-full rounded-lg border bg-surface px-3 py-2.5"
                  />
                </label>
                <label className="mt-4 block text-sm font-medium">
                  来源文件
                  <span className="mt-1 block text-xs font-normal text-muted-foreground">
                    支持 .txt、.md、.zip，最大 20MB
                  </span>
                  <input
                    required
                    type="file"
                    accept=".txt,.md,.zip"
                    onChange={(event) =>
                      setFile(event.target.files?.[0] || null)
                    }
                    className="mt-2 block w-full"
                    id="source-file"
                  />
                </label>
                {kind === "imported_novel" && (
                  <a
                    href="/templates/novel-import-template.txt"
                    download="小说导入章节模板.txt"
                    className="mt-3 inline-flex text-xs font-medium text-brand hover:underline"
                  >
                    下载小说 TXT 模板（含章节标题示例）
                  </a>
                )}
              </>
            )}
            <div className="mt-6 flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                {kind === "original_story"
                  ? "创建后可直接生成并开始体验，详细设定也可以稍后补充。"
                  : "导入后可选择章节或资料片段生成体验副本。"}
              </p>
              <button
                disabled={busy}
                className="shrink-0 rounded-lg bg-foreground px-4 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {busy
                  ? "正在建立…"
                  : kind === "original_story"
                    ? "创建并进入故事"
                    : "导入资料"}
              </button>
            </div>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            {pendingTemplate && (
              <div
                className="fixed inset-0 z-[60] grid place-items-center bg-black/45 p-4"
                onMouseDown={(event) => event.stopPropagation()}
              >
                <section
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="template-replace-title"
                  className="w-full max-w-md rounded-[18px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"
                >
                  <p className="text-xs font-medium text-brand">切换人生起点</p>
                  <h3
                    id="template-replace-title"
                    className="mt-2 text-xl font-semibold"
                  >
                    覆盖当前未保存内容？
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-muted-foreground">
                    切换到「
                    {pendingTemplate === "blank"
                      ? "从空白故事开始"
                      : templateById.get(pendingTemplate)?.title}
                    」会替换正在编辑的故事设定，已经创建的作品不会受到影响。
                  </p>
                  <div className="mt-6 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setPendingTemplate(null)}
                      className="rounded-lg px-3 py-2 text-sm hover:bg-hover"
                    >
                      继续编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => applyTemplate(pendingTemplate)}
                      className="rounded-lg bg-foreground px-3 py-2 text-sm font-medium text-primary-foreground"
                    >
                      覆盖并切换
                    </button>
                  </div>
                </section>
              </div>
            )}
          </form>
        </div>
      )}
    </main>
  );
}
