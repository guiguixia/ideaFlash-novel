import assert from 'node:assert/strict'

/** 与 chapter-view.ts 保持同步的回归断言。 */
function pickActiveWrittenChapter(chapters, selectedId) {
  const written = chapters
    .filter((chapter) => chapter.status === 'accepted')
    .sort((a, b) => a.sequence - b.sequence)
  return written.find((chapter) => chapter.id === selectedId) || written.at(-1) || null
}

const chapters = [
  { id: 'a', status: 'accepted', sequence: 1 },
  { id: 'b', status: 'planned', sequence: 2 },
  { id: 'c', status: 'accepted', sequence: 3 },
]

// 复现：选中非 accepted / 或 status 被本地化后，仍应展示已采纳正文
assert.equal(pickActiveWrittenChapter(chapters, 'b')?.id, 'c')
assert.equal(pickActiveWrittenChapter(chapters, 'a')?.id, 'a')
assert.equal(pickActiveWrittenChapter(chapters, 'c')?.status, 'accepted')
assert.equal(pickActiveWrittenChapter([{ id: 'x', status: 'planned', sequence: 1 }], 'x'), null)
// 误用本地化 status 过滤会得到空列表（旧 bug 的对比断言）
assert.equal(
  chapters.filter((chapter) => chapter.status === 'accepted' || chapter.status === '已采纳').length,
  2,
)
assert.equal(
  [{ id: 'c', status: '已采纳', sequence: 3 }].filter((chapter) => chapter.status === 'accepted').length,
  0,
)

console.log('chapter-view regression ok')
