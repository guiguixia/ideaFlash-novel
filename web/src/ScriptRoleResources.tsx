import { useEffect, useRef, useState } from "react";
import { Download, ImagePlus } from "lucide-react";
import { kernelGet, kernelPost, kernelUpload, kernelUrl } from "./lib/kernel-api";

type Script = {
  id: string;
  title: string;
  sourceStart: number;
  sourceEnd: number;
  status: string;
};

type EmotionSlot = "default" | "thinking" | "puzzled" | "happy" | "low" | "taunting";

type Resource = {
  id: string;
  name: string;
  identity: string;
  imageUrl: string;
  emotionImages: Partial<Record<EmotionSlot, string>>;
  customEmotions: Array<{ id: string; name: string; description: string; imageUrl: string }>;
};

const visualSlots: Array<{ id: EmotionSlot; label: string }> = [
  { id: "default", label: "默认形象" },
  { id: "thinking", label: "思考" },
  { id: "puzzled", label: "疑惑" },
  { id: "happy", label: "开心" },
  { id: "low", label: "低落" },
  { id: "taunting", label: "嘲讽" },
];

export function ScriptRoleResources({
  workId,
  scriptId,
  scripts,
  imported,
  onScriptChange,
}: {
  workId: string;
  scriptId: string;
  scripts: Script[];
  imported: boolean;
  onScriptChange: (scriptId: string) => void;
}) {
  const [rows, setRows] = useState<Resource[]>([]);
  const [error, setError] = useState("");
  const [managingResourceId, setManagingResourceId] = useState<string | null>(null);
  const [target, setTarget] = useState<{ resourceId: string; slot: string; custom: boolean } | null>(null);
  const [customName, setCustomName] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!scriptId) {
      setRows([]);
      setManagingResourceId(null);
      return;
    }
    void kernelGet<Resource[]>(`/api/works/${workId}/scripts/${scriptId}/role-cards`)
      .then(setRows)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "加载剧情资源失败"));
  }, [workId, scriptId]);

  const selectImage = (resourceId: string, slot: string, custom = false) => {
    setTarget({ resourceId, slot, custom });
    input.current?.click();
  };

  const upload = async (file: File) => {
    if (!target) return;
    try {
      const data = new FormData();
      data.append("file", file);
      const next = await kernelUpload<Resource>(
        target.custom
          ? `/api/works/${workId}/scripts/${scriptId}/role-cards/${target.resourceId}/custom-emotions/${target.slot}/image`
          : `/api/works/${workId}/scripts/${scriptId}/role-cards/${target.resourceId}/image?slot=${target.slot}`,
        data,
      );
      setRows((current) => current.map((row) => (row.id === next.id ? next : row)));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传形象失败");
    } finally {
      setTarget(null);
    }
  };

  const createCustomEmotion = async () => {
    if (!managingResource || !customName.trim()) return;
    try {
      const next = await kernelPost<Resource>(
        `/api/works/${workId}/scripts/${scriptId}/role-cards/${managingResource.id}/custom-emotions`,
        { name: customName.trim(), description: customDescription.trim() },
      );
      setRows((current) => current.map((row) => (row.id === next.id ? next : row)));
      setCustomName("");
      setCustomDescription("");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "新增自定义状态失败");
    }
  };

  if (!scriptId) {
    return <section className="rounded-2xl border border-border bg-card p-6 text-sm text-muted-foreground">请先在剧情生成中创建一段剧情。</section>;
  }

  const managingResource = rows.find((row) => row.id === managingResourceId) ?? null;

  return (
    <section className="space-y-5 rounded-2xl border border-border bg-card p-6 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold text-brand">剧情资源</p>
          <h2 className="mt-1 text-xl font-semibold">剧情与画面中的出场角色</h2>
          <p className="mt-1 text-sm text-muted-foreground">上传默认形象和状态图，供剧情体验中的替换角色与场景画面使用；此处不提供角色对话。</p>
        </div>
        <label className="flex items-center gap-2 rounded-lg border border-brand-border bg-brand-soft px-3 py-1.5 text-xs font-semibold text-brand">
          当前剧情
          <select
            value={scriptId}
            onChange={(event) => onScriptChange(event.target.value)}
            className="min-w-56 rounded-md border border-brand-border bg-workspace px-3 py-1.5 text-sm font-normal text-foreground"
            aria-label="当前剧情"
          >
            {scripts.map((script) => (
              <option key={script.id} value={script.id}>
                {script.title}（第 {script.sourceStart}-{script.sourceEnd} 章）
              </option>
            ))}
          </select>
        </label>
      </header>

      {error && <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p>}

      {!imported ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-muted-foreground">导入来源资料后，系统会从剧情中识别出场角色。</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-sm text-muted-foreground">这段剧情暂未识别出角色资源。</p>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {rows.map((row) => (
            <article key={row.id} className="flex h-28 min-w-0 items-center rounded-xl border border-border bg-workspace/40 p-4">
              <div className="flex w-full items-center gap-3">
                <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-card text-muted-foreground">
                  {row.imageUrl ? <img src={kernelUrl(row.imageUrl)} alt={row.name} className="h-full w-full object-cover" /> : <ImagePlus size={18} />}
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold">{row.name}</h3>
                  <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{row.identity || "剧情出场角色"}</p>
                  <button
                    type="button"
                    onClick={() => setManagingResourceId(row.id)}
                    className="mt-1.5 rounded-md border border-brand-border px-2 py-0.5 text-xs font-medium text-brand hover:bg-brand-soft"
                  >
                    管理形象
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {managingResource && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/20 p-4" role="presentation" onMouseDown={() => setManagingResourceId(null)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="role-visual-dialog-title"
            className="max-h-[min(720px,calc(100vh-2rem))] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-workspace p-5 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold text-brand">角色形象</p>
                <h3 id="role-visual-dialog-title" className="mt-1 text-lg font-semibold">{managingResource.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">配置剧情体验中随角色状态切换的形象。</p>
              </div>
              <button type="button" onClick={() => setManagingResourceId(null)} className="rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-active hover:text-foreground" aria-label="关闭形象管理">
                关闭
              </button>
            </header>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {[
                ...visualSlots.map((slot) => ({ id: slot.id, label: slot.label, imagePath: slot.id === "default" ? managingResource.imageUrl : managingResource.emotionImages?.[slot.id], custom: false })),
                ...managingResource.customEmotions.map((slot) => ({ id: slot.id, label: slot.name, imagePath: slot.imageUrl, custom: true })),
              ].map((slot) => {
                return (
                  <div key={slot.id} className="flex h-20 items-center gap-3 rounded-lg border border-border bg-workspace/40 p-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-card text-muted-foreground">
                      {slot.imagePath ? (
                        <button type="button" onClick={() => setPreview({ url: slot.imagePath || "", title: `${managingResource.name} · ${slot.label}` })} className="h-full w-full"><img src={kernelUrl(slot.imagePath)} alt={`${managingResource.name}${slot.label}形象`} className="h-full w-full object-cover" /></button>
                      ) : (
                        <ImagePlus size={16} />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{slot.label}</p>
                      <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{slot.custom ? managingResource.customEmotions.find((item) => item.id === slot.id)?.description || "自定义状态" : slot.imagePath ? "已配置" : "未配置"}</p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {slot.imagePath && <a href={kernelUrl(slot.imagePath)} download={`${managingResource.name}-${slot.label}`} title={`下载${slot.label}形象`} className="rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-hover"><Download className="size-3" /></a>}
                      <button type="button" onClick={() => selectImage(managingResource.id, slot.id, slot.custom)} className="rounded-md border border-brand-border px-2 py-1 text-xs font-medium text-brand hover:bg-brand-soft">
                        {slot.imagePath ? "替换" : "上传"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            {managingResource.customEmotions.length < 5 && (
              <div className="mt-4 border-t border-border pt-4">
                <p className="text-sm font-medium">新增自定义状态</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]">
                  <input value={customName} onChange={(event) => setCustomName(event.target.value)} maxLength={40} placeholder="例如：战斗" className="rounded-md border border-input bg-workspace px-3 py-2 text-sm" />
                  <input value={customDescription} onChange={(event) => setCustomDescription(event.target.value)} maxLength={300} placeholder="状态说明（可选）" className="rounded-md border border-input bg-workspace px-3 py-2 text-sm" />
                  <button type="button" disabled={!customName.trim()} onClick={() => void createCustomEmotion()} className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-brand-foreground disabled:cursor-not-allowed disabled:opacity-50">新增</button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {preview && <div className="fixed inset-0 z-[60] grid place-items-center bg-foreground/70 p-6" onMouseDown={() => setPreview(null)}><figure className="max-h-full max-w-full" onMouseDown={(event) => event.stopPropagation()}><img src={kernelUrl(preview.url)} alt={preview.title} className="max-h-[82vh] max-w-[82vw] rounded-xl bg-workspace object-contain shadow-2xl" /><figcaption className="mt-3 text-center text-sm text-white">{preview.title} · 点击空白处关闭</figcaption></figure></div>}
      <input
        ref={input}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.currentTarget.value = "";
          if (file) void upload(file);
        }}
      />
    </section>
  );
}
