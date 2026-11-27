import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { STATUS, money, vnDate } from "../../lib/format";
import { admin, useSession } from "../api";
import { Card, Stat } from "../ui";

const ACTIVE = new Set(["paid", "preparing", "delivering"]);

export function DashboardPage() {
  const session = useSession()!;
  const today = vnDate(0);
  const orders = useQuery({ queryKey: ["admin-orders", "", today], queryFn: () => admin.orders({ delivery_date: today }), refetchInterval: 30_000 });
  const urgency = useQuery({ queryKey: ["urgency"], queryFn: admin.urgency });
  const review = useQuery({ queryKey: ["batches", "needs_review"], queryFn: () => admin.batches({ status: "needs_review" }) });
  const audit = useQuery({ queryKey: ["audit"], queryFn: admin.audit, enabled: session.role === "owner" });

  if (orders.isPending) return <Loading />;
  if (orders.error) return <ErrorBox message={friendlyError(orders.error)} onRetry={() => orders.refetch()} />;

  const list = orders.data.items;
  const todo = list.filter((o) => ACTIVE.has(o.status));
  const revenue = list.filter((o) => o.status !== "cancelled" && o.status !== "expired").reduce((n, o) => n + o.total, 0);
  const bySlot = new Map<string, typeof list>();
  for (const o of todo) {
    const key = new Date(o.delivery_starts_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
    bySlot.set(key, [...(bySlot.get(key) ?? []), o]);
  }
  // Chỉ tính loại hoa đang thực sự được giảm (dư dưới ngưỡng tối thiểu thì không giảm)
  const hot = (urgency.data ?? []).filter((u) => u.discount_pct > 0);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Chào {session.fullName} 👋</h1>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Đơn giao hôm nay" value={list.length} />
        <Stat label="Cần xử lý" value={todo.length} hint="đã trả tiền · đang bó · đang giao" />
        <Stat label="Doanh thu hôm nay" value={money(revenue)} />
        <Stat label="Hoa cần bán gấp" value={hot.length} hint={hot.length ? "đang tự giảm giá" : "không có"} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Việc hôm nay theo khung giờ" action={<Link to="/admin/don-hang" className="text-sm font-semibold text-rose-700">Tất cả →</Link>}>
          {todo.length === 0 && <p className="text-sm text-stone-500">Không còn đơn nào cần xử lý hôm nay 🎉</p>}
          <div className="space-y-3">
            {[...bySlot.entries()].sort().map(([slot, items]) => (
              <div key={slot}>
                <p className="mb-1 text-sm font-semibold text-stone-600">Khung {slot}</p>
                <ul className="space-y-1">
                  {items.map((o) => (
                    <li key={o.id}>
                      <Link to={`/admin/don-hang/${o.id}`} className="flex min-h-11 items-center justify-between rounded-xl px-3 hover:bg-stone-50">
                        <span><span className="font-mono text-sm font-semibold">{o.code}</span> · {o.customer_name} · {o.item_count} bó</span>
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[o.status].tone}`}>{STATUS[o.status].label}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="🔥 Cần bán gấp" action={<Link to="/admin/gia" className="text-sm font-semibold text-rose-700">Chi tiết →</Link>}>
            {hot.length === 0 ? <p className="text-sm text-stone-500">Không loại hoa nào dư thừa sắp hết hạn.</p> : (
              <ul className="space-y-1 text-sm">
                {hot.map((u) => (
                  <li key={u.flower_type_id} className="flex justify-between">
                    <span>{u.name}</span>
                    <span className="tabular-nums text-stone-600">dư {u.surplus} cành · giảm {u.discount_pct}%</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Lô cần xem xét" action={<Link to="/admin/kho" className="text-sm font-semibold text-rose-700">Kho →</Link>}>
            {review.data?.length ? (
              <ul className="space-y-1 text-sm">
                {review.data.map((b) => (
                  <li key={b.id} className="flex justify-between"><span>Lô #{b.id} · {b.flower_type.name}</span><span className="tabular-nums">{b.quantity_available} cành quá hạn</span></li>
                ))}
              </ul>
            ) : <p className="text-sm text-stone-500">Không có lô quá hạn chờ xử lý.</p>}
          </Card>
          {audit.data && (
            <p className={`rounded-xl px-3 py-2 text-sm ${audit.data.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}>
              {audit.data.ok ? "✓" : "⚠"} Sổ kho {audit.data.ok ? "khớp" : "LỆCH"} trên {audit.data.batches_checked.toLocaleString("vi-VN")} lô
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
