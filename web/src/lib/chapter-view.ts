/** 已写章节阅读态：只展示 accepted，并按选中 id 回退到最近一章。 */
export function pickActiveWrittenChapter<T extends { id: string; status: string; sequence: number }>(
  chapters: T[],
  selectedId?: string | null,
): T | null {
  const written = chapters
    .filter((chapter) => chapter.status === 'accepted')
    .sort((a, b) => a.sequence - b.sequence)
  return written.find((chapter) => chapter.id === selectedId) || written.at(-1) || null
}
