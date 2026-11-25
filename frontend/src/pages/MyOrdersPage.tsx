import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import { Empty } from "../components/ui";
import { STATUS, money, timeRange } from "../lib/format";
import { savedOrders } from "../lib/orders";

export function MyOrdersPage() {
  const saved = savedOrders();
  const results = useQueries({
    queries: saved.map((o) => ({
      queryKey: ["order", o.token],
      queryFn: () => api.track(o.token),
      retry: false,
    })),
  });

  if (saved.length === 0)
    return (
      <Empty icon="📦" title="Chưa có đơn nào trên máy này">
        <Link to="/" className="font-semibold text-rose-700">
          Chọn một bó hoa →
        </Link>
      </Empty>
    );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Đơn của tôi</h1>
      <p className="text-sm text-stone-500">
        Đơn đặt trên trình duyệt này. Shop không cần tài khoản — giữ link theo dõi để xem trên
        máy khác.
      </p>
      <ul className="space-y-3">
        {saved.map((s, i) => {
          const o = results[i].data;
          return (
            <li key={s.code}>
              <Link
                to={`/don/${s.token}`}
                className="block rounded-2xl bg-white p-4 ring-1 ring-stone-100 hover:ring-rose-200"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold">{s.code}</span>
                  {o && (
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[o.status].tone}`}>
                      {STATUS[o.status].label}
                    </span>
                  )}
                </div>
                {o && (
                  <p className="mt-1 text-sm text-stone-600">
                    {timeRange(o.delivery_starts_at, o.delivery_ends_at)} · {money(o.total)}
                  </p>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
