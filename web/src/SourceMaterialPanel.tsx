import { useEffect, useState } from 'react'
import { kernelGet } from './lib/kernel-api'

type Segment = { id: string; sequence: number; title: string; content: string }
type SegmentPage = { items: Segment[]; page: number; pageSize: number; total: number; totalPages: number }

export function SourceMaterialPanel({ workId, total }: { workId: string; total: number }) {
  const [data, setData] = useState<SegmentPage | null>(null)
  const [page, setPage] = useState(1)
  const [pageInput, setPageInput] = useState('1')
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    setError('')
    void kernelGet<SegmentPage>(`/api/works/${workId}/segments?page=${page}&page_size=20`)
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '资料加载失败'))
  }, [workId, page])

  useEffect(() => setPageInput(String(page)), [page])

  function jump() {
    if (!data) return
    const target = Number(pageInput)
    if (!Number.isFinite(target)) { setPageInput(String(page)); return }
    setPage(Math.max(1, Math.min(Math.trunc(target), data.totalPages)))
  }

  return <section className="rounded-[18px] border border-border bg-workspace p-6">
    <p className="text-xs text-brand">来源资料</p>
    <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
      <div><h2 className="text-xl font-semibold">按页浏览资料片段</h2><p className="mt-2 text-sm text-muted-foreground">共 {total} 段，每页 20 段。生成体验副本时可填写连续片段范围。</p></div>
      {data && <p className="text-xs text-muted-foreground">第 {data.page} / {data.totalPages} 页</p>}
    </div>
    {error && <p className="mt-5 text-sm text-destructive">{error}</p>}
    {!data && !error && <p className="mt-5 text-sm text-muted-foreground">正在加载资料…</p>}
    <div className="mt-5 space-y-2">
      {data?.items.map(segment => <details key={segment.id} className="rounded-lg bg-active p-3">
        <summary className="cursor-pointer text-sm font-medium">第 {segment.sequence} 段 · {segment.title}</summary>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{segment.content.slice(0, 1200)}{segment.content.length > 1200 ? '…' : ''}</p>
      </details>)}
    </div>
    {data && <nav className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
      <button disabled={data.page <= 1} onClick={() => setPage(value => value - 1)} className="rounded-lg border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
      <div className="flex items-center gap-2 text-sm text-muted-foreground"><span>显示第 {(data.page - 1) * data.pageSize + 1}–{Math.min(data.page * data.pageSize, data.total)} 段</span><label className="flex items-center gap-1">跳至<input aria-label="跳至页码" inputMode="numeric" value={pageInput} onChange={event => setPageInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); jump() } }} className="w-14 rounded-md border bg-surface px-2 py-1 text-center text-sm"/>页</label><button onClick={jump} className="rounded-md border px-2 py-1 text-xs hover:bg-hover">前往</button></div>
      <button disabled={data.page >= data.totalPages} onClick={() => setPage(value => value + 1)} className="rounded-lg border px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
    </nav>}
  </section>
}
