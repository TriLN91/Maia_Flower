import { useEffect, useState } from "react";
import { apiUrl } from "../api/base";

/**
 * Bản demo chạy gói miễn phí: API "ngủ" sau 15 phút không có truy cập và mất ~1 phút để thức.
 * Web (Static Site) thì hiện ngay — banner này báo cho khách biết vì sao dữ liệu chưa tới,
 * thay vì để họ nhìn spinner mà tưởng web hỏng.
 */
export function ServerWakeBanner() {
  const [state, setState] = useState<"checking" | "slow" | "ready" | "down">("checking");

  useEffect(() => {
    let done = false;
    const slowTimer = window.setTimeout(() => !done && setState("slow"), 2500);
    const ctrl = new AbortController();
    const giveUp = window.setTimeout(() => ctrl.abort(), 120_000);
    fetch(apiUrl("/health"), { signal: ctrl.signal, cache: "no-store" })
      .then((r) => setState(r.ok ? "ready" : "down"))
      .catch(() => setState("down"))
      .finally(() => {
        done = true;
        window.clearTimeout(slowTimer);
        window.clearTimeout(giveUp);
      });
    return () => {
      done = true;
      ctrl.abort();
      window.clearTimeout(slowTimer);
      window.clearTimeout(giveUp);
    };
  }, []);

  if (state === "slow")
    return (
      <div role="status" className="flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-center text-sm text-amber-900">
        <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
        Máy chủ demo đang khởi động (gói miễn phí, khoảng 1 phút) — dữ liệu sẽ tự hiện, bạn đợi chút nhé.
      </div>
    );
  if (state === "down")
    return (
      <div role="alert" className="bg-red-100 px-4 py-2 text-center text-sm text-red-900">
        Không kết nối được máy chủ. Bạn tải lại trang sau ít phút nhé.
      </div>
    );
  return null;
}
