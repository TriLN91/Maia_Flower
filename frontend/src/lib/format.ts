import type { OrderStatus } from "../api/types";

const vnd = new Intl.NumberFormat("vi-VN");
export const money = (n: number) => `${vnd.format(n)}đ`;

const TZ = "Asia/Ho_Chi_Minh";

export const timeRange = (start: string, end: string) => {
  const t = (iso: string) =>
    new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
  const d = new Date(start).toLocaleDateString("vi-VN", {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    timeZone: TZ,
  });
  return `${t(start)}–${t(end)}, ${d}`;
};

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    timeZone: TZ,
  });

/** Ngày hôm nay theo giờ VN dạng YYYY-MM-DD, cộng thêm `offset` ngày. */
export function vnDate(offset = 0): string {
  const d = new Date(Date.now() + offset * 86_400_000);
  return d.toLocaleDateString("en-CA", { timeZone: TZ });
}

export const dayLabel = (iso: string, offset: number) => {
  if (offset === 0) return "Hôm nay";
  if (offset === 1) return "Ngày mai";
  const d = new Date(`${iso}T12:00:00+07:00`);
  return d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit" });
};

export const STATUS: Record<OrderStatus, { label: string; tone: string }> = {
  pending_payment: { label: "Chờ thanh toán", tone: "bg-amber-100 text-amber-800" },
  paid: { label: "Đã thanh toán", tone: "bg-emerald-100 text-emerald-800" },
  preparing: { label: "Đang bó hoa", tone: "bg-sky-100 text-sky-800" },
  delivering: { label: "Đang giao", tone: "bg-indigo-100 text-indigo-800" },
  completed: { label: "Đã giao", tone: "bg-emerald-600 text-white" },
  cancelled: { label: "Đã hủy", tone: "bg-stone-200 text-stone-700" },
  expired: { label: "Hết hạn giữ hoa", tone: "bg-stone-200 text-stone-700" },
  needs_refund: { label: "Chờ hoàn tiền", tone: "bg-rose-100 text-rose-800" },
};

/** Màu nền "ảnh" mẫu theo tông hoa chủ đạo (chưa có ảnh thật). */
const PALETTE: Record<string, string> = {
  đỏ: "from-rose-500 to-red-700",
  hồng: "from-pink-300 to-rose-400",
  trắng: "from-stone-100 to-rose-100",
  kem: "from-amber-50 to-orange-200",
  vàng: "from-amber-200 to-yellow-400",
  tím: "from-violet-300 to-purple-500",
  xanh: "from-sky-200 to-teal-300",
};
export const gradientFor = (color: string | undefined) =>
  PALETTE[color ?? ""] ?? "from-rose-200 to-pink-400";
