import { useEffect } from "react";

const BASE = "Maia Flower — Hoa bó tươi mỗi ngày";

/** Tiêu đề tab theo trang (dễ phân biệt khi mở nhiều tab, đẹp hơn khi chia sẻ link). */
export function useTitle(title?: string | null) {
  useEffect(() => {
    document.title = title ? `${title} · Maia Flower` : BASE;
  }, [title]);
}
