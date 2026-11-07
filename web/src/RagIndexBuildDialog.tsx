export type RagIndexPreview = { total: number; completed: number; remaining: number; status: string }

export function RagIndexBuildDialog({ preview, onClose, onConfirm }: { preview: RagIndexPreview; onClose: () => void; onConfirm: () => void }) {
  const continuing = preview.completed > 0
  const complete = preview.remaining === 0
  return <div className="fixed inset-0 z-[70] grid place-items-center bg-black/45 p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="rag-build-title" className="w-full max-w-md rounded-[22px] border border-border bg-workspace p-6 shadow-[var(--shadow-floating-strong)]">
      <p className="text-xs font-medium text-brand">角色知识库</p>
      <h2 id="rag-build-title" className="mt-1 text-xl font-semibold">{complete ? "知识库已构建完成" : continuing ? "继续构建知识库" : "构建角色知识库"}</h2>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{complete ? `共 ${preview.total} 个原文切块均已完成，无需重新调用 Embedding。` : continuing ? `已完成 ${preview.completed} 个原文切块，本次还需构建 ${preview.remaining} 个；已完成内容会保留。` : `本次将把来源资料切分为 ${preview.total} 个原文片块，并逐个生成向量。`}</p>
      <div className="mt-5 grid grid-cols-3 gap-2 rounded-xl bg-active p-3 text-center text-sm"><div><p className="text-xs text-muted-foreground">总计</p><p className="mt-1 font-medium">{preview.total}</p></div><div><p className="text-xs text-muted-foreground">已完成</p><p className="mt-1 font-medium">{preview.completed}</p></div><div><p className="text-xs text-muted-foreground">待构建</p><p className="mt-1 font-medium">{preview.remaining}</p></div></div>
      <div className="mt-6 flex justify-end gap-2">{!complete && <button type="button" onClick={onClose} className="rounded-lg border px-4 py-2 text-sm hover:bg-hover">取消</button>}<button type="button" onClick={complete ? onClose : onConfirm} className="rounded-lg bg-foreground px-4 py-2 text-sm text-primary-foreground">{complete ? "知道了" : continuing ? "继续构建" : "开始构建"}</button></div>
    </section>
  </div>
}
