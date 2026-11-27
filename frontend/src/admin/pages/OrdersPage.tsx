import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import type { OrderStatus } from "../../api/types";
import { Button, ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { STATUS, dateTime, money, timeRange, vnDate } from "../../lib/format";
import { TRANSITIONS, admin, useSession } from "../api";
import { Card, PageTitle, inputCls } from "../ui";

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Tất cả" },
  { value: "paid", label: "Đã thanh toán" },
  { value: "preparing", label: "Đang bó" },
  { value: "delivering", label: "Đang giao" },
  { value: "pending_payment", label: "Chờ thanh toán" },
  { value: "needs_refund", label: "Chờ hoàn tiền" },
  { value: "completed", label: "Đã giao" },
];

export function OrdersPage() {
  const [status, setStatus] = useState("");
  const [date, setDate] = useState(vnDate(0));
  const orders = useQuery({
    queryKey: ["admin-orders", status, date],
    queryFn: () => admin.orders({ status, delivery_date: date }),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <PageTitle>Đơn hàng</PageTitle>
      <div className="mb-3 flex flex-wrap gap-2">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${inputCls} w-auto`} aria-label="Ngày giao" />
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
          {FILTERS.map((f) => (
            <button key={f.value} onClick={() => setStatus(f.value)}
              className={`min-h-11 shrink-0 rounded-xl px-3 text-sm font-semibold ring-1 ${status === f.value ? "bg-rose-600 text-white ring-rose-600" : "bg-white ring-stone-200"}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {orders.isPending && <Loading />}
      {orders.error && <ErrorBox message={friendlyError(orders.error)} />}
      {orders.data && (
        <Card>
          {orders.data.items.length === 0 && <p className="text-sm text-stone-500">Không có đơn nào.</p>}
          <ul className="divide-y divide-stone-100">
            {orders.data.items.map((o) => (
              <li key={o.id}>
                <Link to={`/admin/don-hang/${o.id}`} className="flex min-h-14 flex-wrap items-center justify-between gap-2 py-2 hover:bg-stone-50">
                  <span>
                    <span className="font-mono font-semibold">{o.code}</span>
                    <span className="block text-sm text-stone-500">{timeRange(o.delivery_starts_at, o.delivery_ends_at)} · {o.customer_name} · {o.item_count} bó</span>
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="tabular-nums">{money(o.total)}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[o.status].tone}`}>{STATUS[o.status].label}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

export function OrderDetailPage() {
  const id = Number(useParams().id);
  const session = useSession()!;
  const qc = useQueryClient();
  const order = useQuery({ queryKey: ["admin-order", id], queryFn: () => admin.order(id) });
  const flowers = useQuery({ queryKey: ["flower-types"], queryFn: admin.flowerTypes, staleTime: 300_000 });
  const move = useMutation({
    mutationFn: (to: OrderStatus) => admin.transition(id, to),
    onSuccess: (o) => {
      qc.setQueryData(["admin-order", id], o);
      qc.invalidateQueries({ queryKey: ["admin-orders"] });
    },
  });

  if (order.isPending) return <Loading />;
  if (order.error) return <ErrorBox message={friendlyError(order.error)} />;
  const o = order.data;
  const flowerName = (fid: number) => flowers.data?.find((f) => f.id === fid)?.name ?? `Hoa #${fid}`;
  const actions = TRANSITIONS.filter((t) => t.from === o.status && (!t.ownerOnly || session.role === "owner"));

  return (
    <div className="space-y-4">
      <Link to="/admin/don-hang" className="text-sm font-semibold text-rose-700">← Đơn hàng</Link>
      <PageTitle action={<span className={`rounded-full px-3 py-1 text-sm font-semibold ${STATUS[o.status].tone}`}>{STATUS[o.status].label}</span>}>
        <span className="font-mono">{o.code}</span>
      </PageTitle>

      {actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {actions.map((a) => (
            <Button key={a.to} variant={a.danger ? "secondary" : "primary"} loading={move.isPending && move.variables === a.to}
              onClick={() => (!a.danger || window.confirm(`${a.label} đơn ${o.code}?`)) && move.mutate(a.to)}>
              {a.label}
            </Button>
          ))}
        </div>
      )}
      {move.error && <ErrorBox message={friendlyError(move.error)} />}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Cần bó">
          <ul className="space-y-3">
            {o.items.map((i) => (
              <li key={i.template_id}>
                <p className="font-semibold">{i.template_name} × {i.quantity}</p>
                <ul className="mt-1 space-y-0.5 text-sm text-stone-600">
                  {i.allocations.map((a, k) => (
                    <li key={k} className="flex justify-between">
                      <span>{flowerName(a.flower_type_id)}</span>
                      <span className="tabular-nums">{a.quantity} cành · lô #{a.batch_id}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          {o.card_message && <p className="mt-3 rounded-lg bg-rose-50 p-2 text-sm italic">Thiệp: “{o.card_message}”</p>}
          {o.note && <p className="mt-2 text-sm">Ghi chú: {o.note}</p>}
        </Card>
        <Card title="Giao hàng">
          <dl className="space-y-1 text-sm">
            <div><dt className="inline text-stone-500">Thời gian: </dt><dd className="inline font-semibold">{timeRange(o.delivery_starts_at, o.delivery_ends_at)}</dd></div>
            <div><dt className="inline text-stone-500">Địa chỉ: </dt><dd className="inline">{o.delivery_address}</dd></div>
            <div><dt className="inline text-stone-500">Người đặt: </dt><dd className="inline">{o.customer_name} · <a className="text-rose-700" href={`tel:${o.customer_phone}`}>{o.customer_phone}</a></dd></div>
            {o.recipient_name && <div><dt className="inline text-stone-500">Người nhận: </dt><dd className="inline">{o.recipient_name}{o.recipient_phone && <> · <a className="text-rose-700" href={`tel:${o.recipient_phone}`}>{o.recipient_phone}</a></>}</dd></div>}
            <div><dt className="inline text-stone-500">Tổng: </dt><dd className="inline font-semibold">{money(o.total)}</dd> <span className="text-stone-500">(ship {money(o.delivery_fee)})</span></div>
          </dl>
        </Card>
        <Card title="Lịch sử trạng thái">
          <ol className="space-y-1 text-sm">
            {o.events.map((e, k) => (
              <li key={k} className="flex justify-between gap-2">
                <span>{STATUS[e.to_status].label} <span className="text-stone-400">· {e.actor}</span>{e.note && <span className="block text-xs text-stone-500">{e.note}</span>}</span>
                <span className="shrink-0 text-stone-500">{dateTime(e.created_at)}</span>
              </li>
            ))}
          </ol>
        </Card>
        <Card title="Thanh toán">
          {o.payments.length === 0 ? <p className="text-sm text-stone-500">Chưa có giao dịch.</p> : (
            <ul className="space-y-1 text-sm">
              {o.payments.map((p) => (
                <li key={p.txn_ref} className="flex justify-between gap-2">
                  <span className="font-mono text-xs">{p.txn_ref}</span>
                  <span>{p.status}{p.needs_refund && <b className="ml-1 text-red-600">· cần hoàn</b>}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
