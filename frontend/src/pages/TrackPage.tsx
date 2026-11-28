import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { OrderStatus } from "../api/types";
import { CheckIcon, ClockIcon, GiftIcon, PinIcon, UserIcon } from "../components/icons";
import { OrderItems } from "../components/OrderItems";
import { Button, ErrorBox, Loading } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { useTitle } from "../lib/title";
import { STATUS, dateTime, money, timeRange } from "../lib/format";

const MESSAGE: Partial<Record<OrderStatus, string>> = {
  paid: "Shop đã nhận đơn. Thợ sẽ bắt đầu bó hoa trước giờ giao.",
  preparing: "Thợ đang chọn những cành tươi nhất và bó hoa cho bạn.",
  delivering: "Bó hoa đang trên đường tới nơi nhận.",
  completed: "Hoa đã được giao. Cảm ơn bạn đã chọn Maia!",
};

function CopyLink() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2000);
        } catch {
          /* trình duyệt chặn clipboard: bỏ qua */
        }
      }}
      className="inline-flex min-h-10 items-center gap-1.5 rounded-full bg-white px-4 text-sm font-medium text-stone-700 ring-1 ring-stone-200 hover:ring-stone-300"
    >
      {copied ? <CheckIcon className="size-4 text-sage-700" /> : null}
      {copied ? "Đã sao chép link" : "Sao chép link theo dõi"}
    </button>
  );
}

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
    <span className="font-display text-4xl font-semibold tabular-nums text-ink">
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
  useTitle(order.data ? `Đơn ${order.data.code}` : "Theo dõi đơn");
  const pay = useMutation({
    mutationFn: () => api.startPayment(token),
    onSuccess: (p) => window.location.assign(p.payment_url),
  });

  if (order.isPending) return <Loading />;
  if (order.error)
    return (
      <div className="mx-auto max-w-xl">
        <ErrorBox message={friendlyError(order.error)} onRetry={() => order.refetch()} />
      </div>
    );

  const o = order.data;
  const status = STATUS[o.status];
  const reached = new Set(o.timeline.map((t) => t.to_status));
  const at = (s: OrderStatus) => o.timeline.find((t) => t.to_status === s)?.created_at;
  const current = FLOW.reduce((acc, s, i) => (reached.has(s) ? i : acc), -1);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3 pb-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.18em] text-sage-700">Đơn hàng</p>
          <h1 className="font-display text-3xl font-semibold text-ink">{o.code}</h1>
          <p className="text-sm text-stone-500">Đặt lúc {dateTime(o.created_at)}</p>
        </div>
        <span className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${status.tone}`}>{status.label}</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {MESSAGE[o.status] ? <p className="text-sm text-stone-600">{MESSAGE[o.status]}</p> : <span />}
        <CopyLink />
      </div>

      {o.status === "pending_payment" && o.hold_expires_at && (
        <section className="space-y-3 rounded-3xl bg-paper p-6 text-center ring-1 ring-stone-200/70">
          <p className="flex items-center justify-center gap-2 text-sm text-stone-600">
            <ClockIcon className="text-brand-600" /> Shop đang giữ hoa và khung giờ cho bạn trong
          </p>
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

      {current >= 0 && (
        <section className="rounded-3xl bg-white p-5 ring-1 ring-stone-200/70">
          <ol className="grid grid-cols-4 gap-1">
            {FLOW.map((s, i) => {
              const done = i <= current;
              return (
                <li key={s} className="relative flex flex-col items-center gap-2 text-center">
                  {i > 0 && (
                    <span
                      className={`absolute right-1/2 top-4 h-0.5 w-full -translate-y-1/2 ${i <= current ? "bg-sage-500" : "bg-stone-200"}`}
                      aria-hidden
                    />
                  )}
                  <span
                    className={`relative flex size-8 items-center justify-center rounded-full text-sm ${done ? "bg-sage-500 text-white" : "bg-stone-100 text-stone-400"} ${i === current && s !== "completed" ? "ring-4 ring-sage-100" : ""}`}
                  >
                    {done ? <CheckIcon className="size-4" /> : i + 1}
                  </span>
                  <span className={`text-xs leading-tight ${done ? "font-semibold text-ink" : "text-stone-400"}`}>
                    {STATUS[s].label}
                  </span>
                  {at(s) && <span className="text-[11px] text-stone-400">{dateTime(at(s)!)}</span>}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <section className="space-y-3 rounded-3xl bg-white p-5 text-sm ring-1 ring-stone-200/70">
        <p className="flex gap-3">
          <ClockIcon className="text-sage-700" />
          <span>
            <span className="block text-xs text-stone-500">Giao lúc</span>
            <b className="text-ink">{timeRange(o.delivery_starts_at, o.delivery_ends_at)}</b>
          </span>
        </p>
        <p className="flex gap-3">
          <PinIcon className="text-sage-700" />
          <span>
            <span className="block text-xs text-stone-500">Giao tới</span>
            {o.delivery_address}
          </span>
        </p>
        <p className="flex gap-3">
          <UserIcon className="text-sage-700" />
          <span>
            <span className="block text-xs text-stone-500">Người đặt</span>
            {o.customer_name} · {o.customer_phone_masked}
            {o.recipient_name && (
              <>
                <span className="mt-1 block text-xs text-stone-500">Người nhận</span>
                {o.recipient_name}
              </>
            )}
          </span>
        </p>
        {o.card_message && (
          <p className="flex gap-3 rounded-2xl bg-brand-50 p-3">
            <GiftIcon className="text-brand-600" />
            <span className="font-display italic text-brand-900">“{o.card_message}”</span>
          </p>
        )}
      </section>

      <section className="rounded-3xl bg-white p-5 ring-1 ring-stone-200/70">
        <OrderItems order={o} />
      </section>

      <Link to="/" className="block py-2 text-center font-semibold text-brand-700">
        Tiếp tục mua hoa →
      </Link>
    </div>
  );
}
