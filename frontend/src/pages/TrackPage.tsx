import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { OrderStatus } from "../api/types";
import { Button, ErrorBox, Loading } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { STATUS, dateTime, money, timeRange } from "../lib/format";

const FLOW: OrderStatus[] = ["paid", "preparing", "delivering", "completed"];
const FINAL: OrderStatus[] = ["completed", "cancelled", "expired", "needs_refund"];

function Countdown({ until, onDone }: { until: string; onDone: () => void }) {
  const [left, setLeft] = useState(() => new Date(until).getTime() - Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      const ms = new Date(until).getTime() - Date.now();
      setLeft(ms);
      if (ms <= 0) {
        window.clearInterval(id);
        onDone();
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [until, onDone]);
  const s = Math.max(0, Math.floor(left / 1000));
  return (
    <span className="font-mono text-2xl font-bold tabular-nums">
      {String(Math.floor(s / 60)).padStart(2, "0")}:{String(s % 60).padStart(2, "0")}
    </span>
  );
}

export function TrackPage() {
  const { token = "" } = useParams();
  const order = useQuery({
    queryKey: ["order", token],
    queryFn: () => api.track(token),
    // Đơn chưa xong thì tự làm mới để thấy trạng thái thợ cập nhật
    refetchInterval: (q) => (q.state.data && FINAL.includes(q.state.data.status) ? false : 10_000),
  });
  const pay = useMutation({
    mutationFn: () => api.startPayment(token),
    onSuccess: (p) => window.location.assign(p.payment_url),
  });

  if (order.isPending) return <Loading />;
  if (order.error)
    return <ErrorBox message={friendlyError(order.error)} onRetry={() => order.refetch()} />;

  const o = order.data;
  const status = STATUS[o.status];
  const reached = new Set(o.timeline.map((t) => t.to_status));
  const at = (s: OrderStatus) => o.timeline.find((t) => t.to_status === s)?.created_at;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-stone-500">Mã đơn</p>
          <h1 className="font-mono text-xl font-extrabold">{o.code}</h1>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${status.tone}`}>
          {status.label}
        </span>
      </div>

      {o.status === "pending_payment" && o.hold_expires_at && (
        <section className="space-y-3 rounded-2xl bg-amber-50 p-4 text-center ring-1 ring-amber-200">
          <p className="text-sm text-amber-900">Shop đang giữ hoa và khung giờ cho bạn trong</p>
          <Countdown until={o.hold_expires_at} onDone={() => order.refetch()} />
          <Button className="w-full" loading={pay.isPending} onClick={() => pay.mutate()}>
            Thanh toán {money(o.total)}
          </Button>
          {pay.error && <ErrorBox message={friendlyError(pay.error)} />}
        </section>
      )}
      {o.status === "expired" && (
        <ErrorBox message="Đơn đã hết 15 phút giữ hoa mà chưa thanh toán. Bạn đặt lại đơn mới nhé." />
      )}
      {o.status === "needs_refund" && (
        <ErrorBox message="Shop rất tiếc không thể giao đơn này. Shop sẽ liên hệ hoàn tiền cho bạn." />
      )}

      {FLOW.some((s) => reached.has(s)) && (
        <ol className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-stone-100">
          {FLOW.map((s) => {
            const done = reached.has(s);
            return (
              <li key={s} className="flex items-center gap-3">
                <span
                  className={`flex size-7 items-center justify-center rounded-full text-sm ${done ? "bg-emerald-500 text-white" : "bg-stone-100 text-stone-400"}`}
                >
                  {done ? "✓" : "•"}
                </span>
                <span className={done ? "font-semibold" : "text-stone-400"}>{STATUS[s].label}</span>
                {at(s) && <span className="ml-auto text-xs text-stone-500">{dateTime(at(s)!)}</span>}
              </li>
            );
          })}
        </ol>
      )}

      <section className="space-y-2 rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-100">
        <p>
          <span className="text-stone-500">Giao: </span>
          <b>{timeRange(o.delivery_starts_at, o.delivery_ends_at)}</b>
        </p>
        <p>
          <span className="text-stone-500">Tới: </span>
          {o.delivery_address}
        </p>
        <p>
          <span className="text-stone-500">Người đặt: </span>
          {o.customer_name} · {o.customer_phone_masked}
        </p>
        {o.recipient_name && (
          <p>
            <span className="text-stone-500">Người nhận: </span>
            {o.recipient_name}
          </p>
        )}
        {o.card_message && <p className="rounded-lg bg-rose-50 p-2 italic">“{o.card_message}”</p>}
      </section>

      <dl className="space-y-1 rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-100">
        {o.items.map((i) => (
          <div key={i.template_id} className="flex justify-between">
            <dt>
              {i.template_name} × {i.quantity}
              {i.discount_pct > 0 && <span className="ml-1 text-rose-600">−{i.discount_pct}%</span>}
            </dt>
            <dd className="tabular-nums">{money(i.line_total)}</dd>
          </div>
        ))}
        <div className="flex justify-between">
          <dt>Phí giao hàng</dt>
          <dd className="tabular-nums">{o.delivery_fee ? money(o.delivery_fee) : "Miễn phí"}</dd>
        </div>
        <div className="flex justify-between border-t border-stone-100 pt-2 text-base font-bold">
          <dt>Tổng</dt>
          <dd className="tabular-nums">{money(o.total)}</dd>
        </div>
      </dl>

      <Link to="/" className="block text-center font-semibold text-rose-700">
        Tiếp tục mua hoa →
      </Link>
    </div>
  );
}
