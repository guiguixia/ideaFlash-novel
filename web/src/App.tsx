import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Bot, Eye, EyeOff, QrCode, Settings, Sparkles, X } from "lucide-react";
import {
  HashRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";
import { kernelGet, kernelPatch, kernelPost, kernelUrl } from "./lib/kernel-api";
import { LibraryHome } from "./LibraryHome";
import { RuntimeWorkbench } from "./RuntimeWorkbench";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试";
function ApiKeyField({ value, onChange, shown, onToggle, configured }: { value: string; onChange: (value: string) => void; shown: boolean; onToggle: () => void; configured: boolean }) {
  return <label className="mt-3 block text-sm">API Key<span className="relative mt-1 block"><input type={shown ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} placeholder={configured ? "已保存；如需替换请输入新 Key" : "仅保存在本机"} className="w-full rounded-lg border py-2 pl-3 pr-10" /><button type="button" onClick={onToggle} aria-label={shown ? "隐藏 API Key" : "显示 API Key"} className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted-foreground hover:text-foreground">{shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></span></label>;
}
function CommunityQrPrompt({
  imageUrl,
  onClose,
}: {
  imageUrl: string;
  onClose: () => void;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="community-qr-title"
        className="relative w-full max-w-md overflow-hidden rounded-[22px] border border-border bg-workspace shadow-[var(--shadow-floating-strong)]"
      >
        <button
          type="button"
          aria-label="关闭"
          onClick={onClose}
          className="absolute right-3 top-3 z-10 rounded-full bg-workspace/90 p-1.5 text-destructive shadow-sm hover:bg-destructive hover:text-destructive-foreground"
        >
          <X className="size-4" />
        </button>
        <div className="bg-brand-soft px-7 pb-5 pt-7 text-center">
          <QrCode className="mx-auto size-7 text-brand" />
          <p className="mt-3 text-xs font-medium text-brand">加入交流社群</p>
          <h2 id="community-qr-title" className="mt-1 text-xl font-semibold">
            和其他故事玩家聊聊
          </h2>
        </div>
        <div className="px-7 pb-7 pt-5 text-center">
          <div className="mx-auto flex max-h-[62vh] min-h-52 items-center justify-center rounded-xl border border-border bg-surface p-2">
            {imageFailed ? (
              <p className="px-5 text-sm leading-6 text-muted-foreground">
                二维码暂时无法加载，请稍后再试。
              </p>
            ) : (
              <img
                src={imageUrl}
                alt="微信入群二维码"
                referrerPolicy="no-referrer"
                onError={() => setImageFailed(true)}
                className="max-h-[58vh] max-w-full object-contain"
              />
            )}
          </div>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            微信扫码加入社群，交流故事体验与创作想法。
          </p>
        </div>
      </section>
    </div>
  );
}

function ModelSetupPrompt({
  onClose,
  onOpenSettings,
}: {
  onClose: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/35 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-setup-title"
        className="w-full max-w-md rounded-[22px] border border-border bg-workspace p-7 shadow-[var(--shadow-floating-strong)]"
      >
        <Sparkles className="size-7 text-brand" />
        <p className="mt-5 text-xs font-medium text-brand">首次使用</p>
        <h2 id="model-setup-title" className="mt-1 text-2xl font-semibold">
          先配置你的大模型
        </h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          生成体验副本和故事对话都需要一个 OpenAI
          兼容模型。填写服务地址、模型名和 API Key 后即可开始。
        </p>
        <div className="mt-6 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border px-3 py-2.5 text-sm hover:bg-hover"
          >
            稍后配置
          </button>
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex-1 rounded-lg bg-foreground px-3 py-2.5 text-sm font-medium text-primary-foreground"
          >
            去配置模型
          </button>
        </div>
      </section>
    </div>
  );
}

function NoticeToast({ notice, onDismiss }: { notice: string; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const show = window.requestAnimationFrame(() => setVisible(true));
    const hide = window.setTimeout(() => setVisible(false), 2600);
    const dismiss = window.setTimeout(onDismiss, 3000);
    return () => {
      window.cancelAnimationFrame(show);
      window.clearTimeout(hide);
      window.clearTimeout(dismiss);
    };
  }, [notice, onDismiss]);
  return <div role="status" className={`fixed left-1/2 top-1/4 z-[80] max-w-sm -translate-x-1/2 rounded-xl border border-brand-border bg-brand-soft px-5 py-3 text-sm text-brand shadow-[var(--shadow-floating-strong)] transition-all duration-300 ${visible ? "-translate-y-1/2 opacity-100" : "translate-y-[-45%] opacity-0"}`}>{notice}</div>;
}

function SettingsPage({
  onModelConfigured,
}: {
  onModelConfigured: () => void;
}) {
  const nav = useNavigate();
  const location = useLocation();
  const embeddingGuide = new URLSearchParams(location.search).get("rag") === "1";
  const embeddingSectionRef = useRef<HTMLElement>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com"),
    [model, setModel] = useState("deepseek-v4-pro"),
    [apiKey, setApiKey] = useState(""),
    [apiKeyConfigured, setApiKeyConfigured] = useState(false),
    [embeddingBaseUrl, setEmbeddingBaseUrl] = useState(""),
    [embeddingModel, setEmbeddingModel] = useState(""),
    [embeddingApiKey, setEmbeddingApiKey] = useState(""),
    [embeddingApiKeyConfigured, setEmbeddingApiKeyConfigured] = useState(false),
    [roleImageBaseUrl, setRoleImageBaseUrl] = useState(""),
    [roleImageModel, setRoleImageModel] = useState("wan2.7-image"),
    [roleImageApiKey, setRoleImageApiKey] = useState(""),
    [roleImageApiKeyConfigured, setRoleImageApiKeyConfigured] = useState(false),
    [sceneImageBaseUrl, setSceneImageBaseUrl] = useState(""),
    [sceneImageModel, setSceneImageModel] = useState("wan2.7-image"),
    [sceneImageApiKey, setSceneImageApiKey] = useState(""),
    [sceneImageApiKeyConfigured, setSceneImageApiKeyConfigured] = useState(false),
    [showApiKey, setShowApiKey] = useState(false),
    [showEmbeddingApiKey, setShowEmbeddingApiKey] = useState(false),
    [showRoleImageApiKey, setShowRoleImageApiKey] = useState(false),
    [showSceneImageApiKey, setShowSceneImageApiKey] = useState(false),
    [activeConfig, setActiveConfig] = useState<"model" | "embedding" | "roleImage" | "sceneImage" | null>(null),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [testing, setTesting] = useState(false);
  useEffect(() => {
    void kernelGet<{ baseUrl: string; model: string; apiKey: string; apiKeyConfigured: boolean; embeddingBaseUrl: string; embeddingModel: string; embeddingApiKey: string; embeddingApiKeyConfigured: boolean; roleImageBaseUrl: string; roleImageModel: string; roleImageApiKey: string; roleImageApiKeyConfigured: boolean; sceneImageBaseUrl: string; sceneImageModel: string; sceneImageApiKey: string; sceneImageApiKeyConfigured: boolean }>(
      "/api/settings/llm",
      { cache: "no-store" },
    )
      .then((config) => {
        setBaseUrl(config.baseUrl);
        setModel(config.model);
        setApiKey(config.apiKey);
        setApiKeyConfigured(config.apiKeyConfigured);
        setEmbeddingBaseUrl(config.embeddingBaseUrl);
        setEmbeddingModel(config.embeddingModel);
        setEmbeddingApiKey(config.embeddingApiKey);
        setEmbeddingApiKeyConfigured(config.embeddingApiKeyConfigured);
        setRoleImageBaseUrl(config.roleImageBaseUrl);
        setRoleImageModel(config.roleImageModel || "wan2.7-image");
        setRoleImageApiKey(config.roleImageApiKey);
        setRoleImageApiKeyConfigured(config.roleImageApiKeyConfigured);
        setSceneImageBaseUrl(config.sceneImageBaseUrl);
        setSceneImageModel(config.sceneImageModel || "wan2.7-image");
        setSceneImageApiKey(config.sceneImageApiKey);
        setSceneImageApiKeyConfigured(config.sceneImageApiKeyConfigured);
      })
      .catch((reason) => setError(message(reason)));
  }, [location.key]);
  useEffect(() => {
    if (!embeddingGuide) return;
    const timer = window.setTimeout(() => embeddingSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
    return () => window.clearTimeout(timer);
  }, [embeddingGuide]);
  async function saveConfig(kind: "model" | "embedding" | "roleImage" | "sceneImage") {
    setNotice("");
    setError("");
    if (kind === "embedding" && (!embeddingBaseUrl.trim() || !embeddingModel.trim() || (!embeddingApiKey.trim() && !embeddingApiKeyConfigured))) {
      setError("请完整填写 Embedding 服务地址、模型和 API Key 后再保存。");
      return;
    }
    if (kind === "roleImage" && (!roleImageBaseUrl.trim() || !roleImageModel.trim() || (!roleImageApiKey.trim() && !roleImageApiKeyConfigured))) {
      setError("请完整填写角色图片生成服务地址、模型和 API Key 后再保存。");
      return;
    }
    if (kind === "sceneImage" && (!sceneImageBaseUrl.trim() || !sceneImageModel.trim() || (!sceneImageApiKey.trim() && !sceneImageApiKeyConfigured))) {
      setError("请完整填写剧情图片生成服务地址、模型和 API Key 后再保存。");
      return;
    }
    try {
      await kernelPatch("/api/settings/llm", {
        base_url: baseUrl,
        model,
        api_key: apiKey,
        embedding_base_url: embeddingBaseUrl,
        embedding_model: embeddingModel,
        embedding_api_key: embeddingApiKey,
        role_image_base_url: roleImageBaseUrl,
        role_image_model: roleImageModel,
        role_image_api_key: roleImageApiKey,
        scene_image_base_url: sceneImageBaseUrl,
        scene_image_model: sceneImageModel,
        scene_image_api_key: sceneImageApiKey,
      });
      onModelConfigured();
      if (kind === "roleImage") setRoleImageApiKeyConfigured(true);
      if (kind === "sceneImage") setSceneImageApiKeyConfigured(true);
      if (kind === "model") setApiKeyConfigured(true);
      if (kind === "embedding") setEmbeddingApiKeyConfigured(true);
      setNotice(kind === "embedding" ? "Embedding 配置已保存，可以返回工作台构建知识库。" : kind === "roleImage" ? "角色图片生成模型配置已保存" : kind === "sceneImage" ? "剧情图片生成模型配置已保存" : "大模型配置已保存");
    } catch (reason) {
      setError(message(reason));
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await saveConfig("model");
  }
  async function testConnection(kind: "model" | "embedding" | "roleImage" | "sceneImage" = "model") {
    setNotice("");
    setError("");
    setTesting(true);
    try {
      const values = kind === "embedding" ? [embeddingBaseUrl, embeddingModel, embeddingApiKey] : kind === "roleImage" ? [roleImageBaseUrl, roleImageModel, roleImageApiKey] : kind === "sceneImage" ? [sceneImageBaseUrl, sceneImageModel, sceneImageApiKey] : [baseUrl, model, apiKey];
      if (!values[2] && !(kind === "model" ? apiKeyConfigured : kind === "embedding" ? embeddingApiKeyConfigured : kind === "roleImage" ? roleImageApiKeyConfigured : sceneImageApiKeyConfigured)) throw new Error("请输入 API Key 后再测试连接");
      const result = await kernelPost<{ model: string; replyPreview?: string }>(kind === "model" ? "/api/settings/llm/test" : "/api/settings/connection/test", { base_url: values[0], model: values[1], api_key: values[2], ...(kind === "model" ? {} : { kind: kind === "roleImage" ? "role_image" : kind === "sceneImage" ? "scene_image" : "embedding" }) });
      setNotice(`连接成功 · ${result.model}${result.replyPreview ? ` · ${result.replyPreview}` : ""}`);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setTesting(false);
    }
  }
  function returnToPrevious() {
    const returnTo = new URLSearchParams(location.search).get("returnTo");
    if (returnTo?.startsWith("/workbench?")) {
      nav(returnTo);
      return;
    }
    if (window.history.length > 1) {
      nav(-1);
      return;
    }
    nav("/");
  }
  return (
    <main className="mx-auto max-w-2xl p-6">
      <button
        onClick={returnToPrevious}
        className="flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        返回上一步
      </button>
      {embeddingGuide && <aside role="alert" className="mt-5 rounded-xl border border-brand-border bg-brand-soft px-4 py-3 text-sm leading-6 text-brand">需要先完成 Embedding 配置，保存后即可返回工作台构建角色知识库。</aside>}
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {([['model','大模型','生成副本、剧情与私聊',apiKeyConfigured],['embedding','角色知识库','检索副本前原文资料',embeddingApiKeyConfigured],['roleImage','角色形象生成','生成角色默认与情绪形象',roleImageApiKeyConfigured],['sceneImage','剧情图片生成','生成沉浸演出场景画面',sceneImageApiKeyConfigured]] as const).map(([kind,title,description,configured]) => <button key={kind} type="button" onClick={() => setActiveConfig(kind)} className={`rounded-[18px] border bg-workspace p-5 text-left hover:bg-hover ${embeddingGuide && kind === 'embedding' ? 'border-brand' : ''}`}><div className="flex items-center justify-between gap-3"><p className="font-medium">{title}</p><span className={`rounded-full px-2 py-0.5 text-xs ${configured ? 'bg-brand-soft text-brand' : 'bg-active text-muted-foreground'}`}>{configured ? '已配置' : '未配置'}</span></div><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p><span className="mt-4 inline-block text-sm text-brand">打开配置 →</span></button>)}
      </div>
      {activeConfig && <div className="fixed inset-0 z-[70] grid place-items-center bg-black/40 p-4"><form onSubmit={(event) => { event.preventDefault(); void saveConfig(activeConfig); }} className="w-full max-w-lg rounded-[22px] border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-brand">模型服务配置</p><h2 className="mt-1 text-xl font-semibold">{{model:'大模型',embedding:'角色知识库 Embedding',roleImage:'角色形象生成',sceneImage:'剧情图片生成'}[activeConfig]}</h2><p className="mt-2 text-sm text-muted-foreground">配置仅保存在本机；默认掩码展示，点击小眼睛可查看完整 Key。</p></div><button type="button" onClick={() => setActiveConfig(null)} className="rounded-full p-1 hover:bg-hover"><X className="size-5" /></button></div>{activeConfig === 'model' && <><label className="mt-5 block text-sm">服务地址<input required value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><label className="mt-3 block text-sm">模型名称<input required value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><ApiKeyField value={apiKey} onChange={setApiKey} shown={showApiKey} onToggle={() => setShowApiKey(!showApiKey)} configured={apiKeyConfigured} /></>}{activeConfig === 'embedding' && <><label className="mt-5 block text-sm">服务地址<input required value={embeddingBaseUrl} onChange={(e) => setEmbeddingBaseUrl(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><label className="mt-3 block text-sm">模型名称<input required value={embeddingModel} onChange={(e) => setEmbeddingModel(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><ApiKeyField value={embeddingApiKey} onChange={setEmbeddingApiKey} shown={showEmbeddingApiKey} onToggle={() => setShowEmbeddingApiKey(!showEmbeddingApiKey)} configured={embeddingApiKeyConfigured} /></>}{activeConfig === 'roleImage' && <><label className="mt-5 block text-sm">服务地址<input required value={roleImageBaseUrl} onChange={(e) => setRoleImageBaseUrl(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><label className="mt-3 block text-sm">模型名称<input required value={roleImageModel} onChange={(e) => setRoleImageModel(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><ApiKeyField value={roleImageApiKey} onChange={setRoleImageApiKey} shown={showRoleImageApiKey} onToggle={() => setShowRoleImageApiKey(!showRoleImageApiKey)} configured={roleImageApiKeyConfigured} /></>}{activeConfig === 'sceneImage' && <><label className="mt-5 block text-sm">服务地址<input required value={sceneImageBaseUrl} onChange={(e) => setSceneImageBaseUrl(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><label className="mt-3 block text-sm">模型名称<input required value={sceneImageModel} onChange={(e) => setSceneImageModel(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label><ApiKeyField value={sceneImageApiKey} onChange={setSceneImageApiKey} shown={showSceneImageApiKey} onToggle={() => setShowSceneImageApiKey(!showSceneImageApiKey)} configured={sceneImageApiKeyConfigured} /></>}<div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => void testConnection(activeConfig)} disabled={testing} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-50">{testing ? '测试中…' : '测试连接'}</button><button type="button" onClick={() => setActiveConfig(null)} className="rounded-lg border px-4 py-2 text-sm">取消</button><button className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">保存配置</button></div>{error && <p className="mt-3 text-sm text-destructive">{error}</p>}</form></div>}
      <form
        onSubmit={save}
        className="hidden mt-6 rounded-[18px] border bg-workspace p-6"
      >
        <div className="flex items-start gap-3">
          <Settings className="mt-0.5 size-5 text-brand" />
          <div>
            <p className="text-xs font-medium text-brand">开始前的准备</p>
            <h1 className="mt-1 text-xl font-semibold">大模型配置</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              支持任意 OpenAI 兼容服务。配置仅保存在本机数据库。
            </p>
          </div>
        </div>
        <label className="mt-5 block text-sm">
          服务地址
          <input
            required
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="https://api.example.com/v1"
            className="mt-1 w-full rounded-lg border px-3 py-2"
          />
        </label>
        <label className="mt-3 block text-sm">
          模型名称
          <input
            required
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="例如：deepseek-v4-pro"
            className="mt-1 w-full rounded-lg border px-3 py-2"
          />
        </label>
        <label className="mt-3 block text-sm">
          API Key
          <span className="relative mt-1 block">
            <input
              type={showApiKey ? "text" : "password"}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="留空并保存可清除配置"
              className="w-full rounded-lg border py-2 pl-3 pr-10"
            />
            <button
              type="button"
              onClick={() => setShowApiKey((shown) => !shown)}
              aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"}
              title={showApiKey ? "隐藏 API Key" : "显示 API Key"}
              className="absolute inset-y-0 right-0 grid w-10 place-items-center text-muted-foreground hover:text-foreground"
            >
              {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </span>
        </label>
        <div className="mt-5 flex flex-wrap gap-2">
          <button type="button" onClick={() => void testConnection()} disabled={testing} className="rounded-lg border px-4 py-2 text-sm hover:bg-hover disabled:opacity-50">
            {testing ? "测试中…" : "测试连接"}
          </button>
          <button className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">
            保存大模型配置
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </form>
      <section ref={embeddingSectionRef} className={`hidden mt-4 rounded-[18px] border bg-workspace p-6 ${embeddingGuide ? "border-brand" : ""}`}>
        <p className="text-xs font-medium text-brand">角色知识 RAG（可选）</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{embeddingGuide ? "构建知识库前，请先填写下列 Embedding 配置，再点击上方“保存配置”。" : "用于从导入原文检索角色在副本前已经知道的事实；未配置时角色私聊仍可正常使用。"}</p>
        <label className="mt-4 block text-sm">Embedding 服务地址<input value={embeddingBaseUrl} onChange={(event) => setEmbeddingBaseUrl(event.target.value)} placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">Embedding 模型<input value={embeddingModel} onChange={(event) => setEmbeddingModel(event.target.value)} placeholder="例如：qwen3.7-text-embedding-flash" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">Embedding API Key<input type="password" value={embeddingApiKey} onChange={(event) => setEmbeddingApiKey(event.target.value)} placeholder="仅保存在本机" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <button type="button" onClick={() => void saveConfig("embedding")} className="mt-5 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">保存 Embedding 配置</button>
      </section>
      <section className="hidden mt-4 rounded-[18px] border bg-workspace p-6">
        <p className="text-xs font-medium text-brand">角色形象生成</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">用于根据角色描述和 1—3 张参考图生成默认形象或情绪形象。模型调用将在生成前由你主动发起。</p>
        <label className="mt-4 block text-sm">角色图片生成服务地址<input value={roleImageBaseUrl} onChange={(event) => setRoleImageBaseUrl(event.target.value)} placeholder="https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">角色图片生成模型<input value={roleImageModel} onChange={(event) => setRoleImageModel(event.target.value)} placeholder="例如：wan2.7-image" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">角色图片生成 API Key<input type="password" value={roleImageApiKey} onChange={(event) => setRoleImageApiKey(event.target.value)} placeholder={roleImageApiKeyConfigured ? "已保存；如需替换请输入新 Key" : "仅保存在本机"} className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <button type="button" onClick={() => void saveConfig("roleImage")} className="mt-5 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">保存角色图片生成配置</button>
      </section>
      <section className="hidden mt-4 rounded-[18px] border bg-workspace p-6">
        <p className="text-xs font-medium text-brand">剧情图片生成</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">用于按当前剧情、人物参考图和场景描述生成沉浸体验中的关键剧情插画。模型调用将在生成前由你主动发起。</p>
        <label className="mt-4 block text-sm">剧情图片生成服务地址<input value={sceneImageBaseUrl} onChange={(event) => setSceneImageBaseUrl(event.target.value)} placeholder="https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">剧情图片生成模型<input value={sceneImageModel} onChange={(event) => setSceneImageModel(event.target.value)} placeholder="例如：wan2.7-image" className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <label className="mt-3 block text-sm">剧情图片生成 API Key<input type="password" value={sceneImageApiKey} onChange={(event) => setSceneImageApiKey(event.target.value)} placeholder={sceneImageApiKeyConfigured ? "已保存；如需替换请输入新 Key" : "仅保存在本机"} className="mt-1 w-full rounded-lg border px-3 py-2" /></label>
        <button type="button" onClick={() => void saveConfig("sceneImage")} className="mt-5 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">保存剧情图片生成配置</button>
      </section>
      {notice && <NoticeToast notice={notice} onDismiss={() => setNotice("")} />}
    </main>
  );
}

function WeChatPage() {
  const nav = useNavigate();
  const [wechat, setWechat] = useState<{ status: string; qrDataUrl: string; error: string; hasCredentials: boolean; sdkAvailable: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let timer = 0;
    const load = () => kernelGet<{ status: string; qrDataUrl: string; error: string; hasCredentials: boolean; sdkAvailable: boolean }>("/api/settings/wechat", { cache: "no-store" }).then(setWechat).catch((reason) => setError(message(reason)));
    void load();
    timer = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(timer);
  }, []);
  async function connect(force = false) {
    setBusy(true); setError("");
    try { setWechat(await kernelPost<{ status: string; qrDataUrl: string; error: string; hasCredentials: boolean; sdkAvailable: boolean }>(`/api/settings/wechat/connect${force ? "?force=true" : ""}`, {})); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true); setError("");
    try { setWechat(await kernelPost<{ status: string; qrDataUrl: string; error: string; hasCredentials: boolean; sdkAvailable: boolean }>("/api/settings/wechat/disconnect", {})); }
    catch (reason) { setError(message(reason)); }
    finally { setBusy(false); }
  }
  const connected = wechat?.status === "connected";
  const waiting = wechat?.status === "pending" || wechat?.status === "scanned";
  return <main className="mx-auto max-w-2xl p-6"><button type="button" onClick={() => nav(-1)} className="flex items-center gap-1 text-sm"><ArrowLeft className="size-4" />返回上一步</button><section className="mt-6 overflow-hidden rounded-[22px] border bg-workspace shadow-sm"><div className="bg-brand-soft px-7 py-6"><Bot className="size-7 text-brand" /><p className="mt-4 text-xs font-medium text-brand">WeChat</p><h1 className="mt-1 text-2xl font-semibold">微信接入</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">连接一个微信机器人，让朋友通过文字菜单体验剧情、与角色私聊。</p></div><div className="p-7"><div className="flex items-center justify-between gap-4 rounded-xl border bg-surface px-4 py-3"><div><p className="text-sm font-medium">连接状态</p><p className="mt-1 text-xs text-muted-foreground">{connected ? "机器人正在接收微信消息" : waiting ? "请使用微信扫码确认" : "尚未连接机器人"}</p></div><span className={`rounded-full px-2.5 py-1 text-xs ${connected ? "bg-brand-soft text-brand" : "bg-active text-muted-foreground"}`}>{connected ? "已连接" : waiting ? "等待扫码" : "未连接"}</span></div>{!wechat?.sdkAvailable && <p className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">微信依赖未安装，请更新本地依赖后重试。</p>}{waiting && (wechat?.qrDataUrl ? <img src={wechat.qrDataUrl} alt="微信机器人登录二维码" className="mx-auto mt-6 size-64 rounded-xl border bg-white p-2" /> : <p className="mt-6 text-center text-sm text-muted-foreground">正在获取二维码…</p>)}{(wechat?.error || error) && <p className="mt-4 text-sm text-destructive">{wechat?.error || error}</p>}<div className="mt-6 flex flex-wrap gap-2">{connected ? <><button type="button" onClick={() => void connect(true)} disabled={busy} className="rounded-lg border px-4 py-2 text-sm disabled:opacity-50">重新出码</button><button type="button" onClick={() => void disconnect()} disabled={busy} className="rounded-lg border px-4 py-2 text-sm text-destructive disabled:opacity-50">断开连接</button></> : <button type="button" onClick={() => void connect(waiting)} disabled={busy || wechat?.sdkAvailable === false} className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{busy ? "处理中…" : waiting ? "重新出码" : "连接微信"}</button>}</div><div className="mt-7 border-t pt-5 text-sm leading-7 text-muted-foreground"><p className="font-medium text-foreground">连接后如何使用</p><p className="mt-2">微信平台需要用户先发出一条消息才能建立回复通道：首次发送普通消息即可收到首页；也可直接发送【作品】、【剧情】或【私聊】进入对应流程。发送【首页】或【退出】可离开当前会话。</p></div></div></section></main>;
}

function AppRoutes() {
  const nav = useNavigate();
  const [needsModel, setNeedsModel] = useState(false),
    [communityQr, setCommunityQr] = useState(""),
    [showCommunityQr, setShowCommunityQr] = useState(false);
  useEffect(() => {
    void kernelGet<{ imageUrl: string }>("/api/community-qr")
      .then((community) => setCommunityQr(kernelUrl(community.imageUrl)))
      .catch(() => undefined);
    const showModel = () => setNeedsModel(true),
      showCommunity = () => setShowCommunityQr(true);
    window.addEventListener("story:model-required", showModel);
    window.addEventListener("story:open-community-qr", showCommunity);
    return () => {
      window.removeEventListener("story:model-required", showModel);
      window.removeEventListener("story:open-community-qr", showCommunity);
    };
  }, []);
  return (
    <>
      <Routes>
        <Route path="/" element={<LibraryHome />} />
        <Route path="/workbench" element={<RuntimeWorkbench />} />
        <Route
          path="/settings"
          element={
            <SettingsPage onModelConfigured={() => setNeedsModel(false)} />
          }
        />
        <Route path="/wechat" element={<WeChatPage />} />
        <Route path="*" element={<LibraryHome />} />
      </Routes>
      {needsModel ? (
        <ModelSetupPrompt
          onClose={() => setNeedsModel(false)}
          onOpenSettings={() => {
            setNeedsModel(false);
            nav("/settings");
          }}
        />
      ) : (
        communityQr &&
        showCommunityQr && (
          <CommunityQrPrompt
            imageUrl={communityQr}
            onClose={() => setShowCommunityQr(false)}
          />
        )
      )}
    </>
  );
}

export function App() {
  return (
    <HashRouter>
      <AppRoutes />
    </HashRouter>
  );
}
