import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Order } from "../api/types";
import { money } from "../lib/format";
import { BouquetArt } from "./BouquetArt";

/** Danh sách bó trong đơn, kèm hình minh hoạ từng mẫu (dùng ở trang theo dõi & kết quả). */
export function OrderItems({ order, showTotals = true }: { order: Order; showTotals?: boolean }) {
  const catalog = useQuery({ queryKey: ["templates", "name"], queryFn: () => api.templates("name") });
  const byId = new Map((catalog.data?.items ?? []).map((t) => [t.id, t]));
  return (
    <div className="space-y-3 text-sm">
      <ul className="space-y-3">
        {order.items.map((i) => {
          const t = byId.get(i.template_id);
          return (
            <li key={i.template_id} className="flex items-center gap-3">
              <span className="relative w-12 shrink-0 overflow-hidden rounded-xl bg-paper">
                {t ? <BouquetArt template={t} /> : <span className="block aspect-[4/5]" />}
                <span className="absolute -right-0.5 -top-0.5 min-w-5 rounded-full bg-ink px-1 text-center text-[11px] font-bold leading-5 text-white">
                  {i.quantity}
                </span>
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-ink">{i.template_name}</span>
                {i.discount_pct > 0 && (
                  <span className="text-xs font-semibold text-brand-700">Ưu đãi −{i.discount_pct}%</span>
                )}
              </span>
              <span className="tabular-nums">{money(i.line_total)}</span>
            </li>
          );
        })}
      </ul>
      {showTotals && (
        <dl className="space-y-2 border-t border-stone-100 pt-3">
          <div className="flex justify-between">
            <dt className="text-stone-500">Phí giao hàng</dt>
            <dd className="tabular-nums">{order.delivery_fee ? money(order.delivery_fee) : "Miễn phí"}</dd>
          </div>
          <div className="flex justify-between border-t border-stone-100 pt-3 text-base font-bold">
            <dt>Tổng</dt>
            <dd className="tabular-nums">{money(order.total)}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
