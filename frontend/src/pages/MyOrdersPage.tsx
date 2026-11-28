import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api/client";
import { ArrowRightIcon, ReceiptIcon } from "../components/icons";
import { Empty } from "../components/ui";
import { STATUS, money, timeRange } from "../lib/format";
import { savedOrders } from "../lib/orders";
import { useTitle } from "../lib/title";

export function MyOrdersPage() {
  useTitle("Đơn của tôi");
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
      <Empty icon={<ReceiptIcon className="size-9" />} title="Chưa có đơn nào trên máy này">
        <Link to="/" className="mt-3 inline-flex items-center gap-1 font-semibold text-brand-700">
          Chọn một bó hoa <ArrowRightIcon className="size-4" />
        </Link>
      </Empty>
    );

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="font-display text-3xl font-semibold text-ink sm:text-4xl">Đơn của tôi</h1>
        <p className="mt-1 text-sm text-stone-500">
          Đơn đặt trên trình duyệt này. Không cần tài khoản: giữ đường link theo dõi để xem trên máy khác.
        </p>
      </div>
      <ul className="space-y-3">
        {saved.map((s, i) => {
          const o = results[i].data;
          return (
            <li key={s.code}>
              <Link
                to={`/don/${s.token}`}
                className="flex items-center gap-4 rounded-3xl bg-white p-4 ring-1 ring-stone-200/70 transition hover:ring-brand-200"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                  <ReceiptIcon />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-ink">{s.code}</span>
                    {o && (
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[o.status].tone}`}>
                        {STATUS[o.status].label}
                      </span>
                    )}
                  </span>
                  {o && (
                    <span className="mt-0.5 block text-sm text-stone-500">
                      {timeRange(o.delivery_starts_at, o.delivery_ends_at)} · {money(o.total)}
                    </span>
                  )}
                </span>
                <ArrowRightIcon className="size-4 text-stone-400" />
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
