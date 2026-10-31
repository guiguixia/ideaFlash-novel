import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, Eye, EyeOff, QrCode, Settings, Sparkles, X } from "lucide-react";
import {
  HashRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";
import { kernelGet, kernelPatch } from "./lib/kernel-api";
import { LibraryHome } from "./LibraryHome";
import { RuntimeWorkbench } from "./RuntimeWorkbench";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试";
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

function SettingsPage({
  onModelConfigured,
}: {
  onModelConfigured: () => void;
}) {
  const nav = useNavigate();
  const location = useLocation();
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com"),
    [model, setModel] = useState("deepseek-v4-pro"),
    [apiKey, setApiKey] = useState(""),
    [showApiKey, setShowApiKey] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    void kernelGet<{ baseUrl: string; model: string; apiKey: string }>(
      "/api/settings/llm",
      { cache: "no-store" },
    )
      .then((config) => {
        setBaseUrl(config.baseUrl);
        setModel(config.model);
        setApiKey(config.apiKey);
      })
      .catch((reason) => setError(message(reason)));
  }, [location.key]);
  async function save(event: FormEvent) {
    event.preventDefault();
    setNotice("");
    setError("");
    try {
      await kernelPatch("/api/settings/llm", {
        base_url: baseUrl,
        model,
        api_key: apiKey,
      });
      onModelConfigured();
      setNotice("大模型配置已保存");
    } catch (reason) {
      setError(message(reason));
    }
  }
  return (
    <main className="mx-auto max-w-2xl p-6">
      <button
        onClick={() => nav("/")}
        className="flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        返回我的作品
      </button>
      <form
        onSubmit={save}
        className="mt-6 rounded-[18px] border bg-workspace p-6"
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
        <button className="mt-5 rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">
          保存配置
        </button>
        {notice && <p className="mt-3 text-sm text-success">{notice}</p>}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </form>
    </main>
  );
}

function AppRoutes() {
  const nav = useNavigate();
  const [needsModel, setNeedsModel] = useState(false),
    [communityQr, setCommunityQr] = useState(""),
    [showCommunityQr, setShowCommunityQr] = useState(false);
  useEffect(() => {
    void kernelGet<{ imageUrl: string }>("/api/community-qr")
      .then((community) => setCommunityQr(community.imageUrl))
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
