/** Evidences rendered per UI page (avoids mounting thousands of DOM nodes). */
export const EVIDENCE_UI_PAGE_SIZE = 80;

export function paginateItems<T>(items: T[], page: number, pageSize = EVIDENCE_UI_PAGE_SIZE) {
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const start = safePage * pageSize;
  return {
    page: safePage,
    pageCount,
    pageSize,
    total: items.length,
    slice: items.slice(start, start + pageSize),
  };
}
