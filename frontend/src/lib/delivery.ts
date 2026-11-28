import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { vnDate } from "./format";

/** Khung giờ giao sớm nhất còn nhận đơn (hôm nay, không thì 1–2 ngày tới) — lấy từ dữ liệu thật
 * của shop, hiện ở trang chủ / trang mẫu để khách biết "đặt bây giờ thì khi nào nhận". */
export function useEarliestSlot() {
  return useQuery({
    queryKey: ["earliest-slot"],
    staleTime: 60_000,
    queryFn: async () => {
      for (const offset of [0, 1, 2]) {
        const slots = await api.slots(vnDate(offset));
        const s = slots.find((x) => x.bookable);
        if (s) return { offset, start: s.start_time.slice(0, 5), end: s.end_time.slice(0, 5) };
      }
      return null;
    },
  });
}

export function earliestLabel(e: { offset: number; start: string; end: string }) {
  const day = e.offset === 0 ? "hôm nay" : e.offset === 1 ? "ngày mai" : "ngày kia";
  return `${e.start}–${e.end} ${day}`;
}
