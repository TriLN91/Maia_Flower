import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, api } from "../api/client";
import { AddressMap, type LatLng } from "../components/AddressMap";
import { BottomBar, Button, Empty, ErrorBox, Loading } from "../components/ui";
import { cart, useCart } from "../lib/cart";
import { friendlyError } from "../lib/errors";
import { dayLabel, money, vnDate } from "../lib/format";
import { saveOrder } from "../lib/orders";

const PHONE_RE = /^(0|\+?84)[35789]\d{8}$/;
const normalizePhone = (s: string) => s.replace(/[\s.\-()]/g, "");

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-stone-100">
      <h2 className="flex items-center gap-2 font-bold">
        <span className="flex size-6 items-center justify-center rounded-full bg-rose-600 text-xs text-white">
          {n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium text-stone-700">{label}</span>
      {children}
      {error && <span className="block text-xs text-red-600">{error}</span>}
    </label>
  );
}

const inputCls =
  "min-h-11 w-full rounded-xl border-0 px-3 ring-1 ring-stone-200 focus:ring-2 focus:ring-rose-400";

export function CheckoutPage() {
  const lines = useCart();
  const navigate = useNavigate();
  const shop = useQuery({ queryKey: ["shop-info"], queryFn: api.shopInfo, staleTime: 300_000 });

  const [pos, setPos] = useState<LatLng | null>(null);
  const [address, setAddress] = useState("");
  const [date, setDate] = useState(vnDate(0));
  const [slotId, setSlotId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [gift, setGift] = useState(false);
  const [recipientName, setRecipientName] = useState("");
  const [recipientPhone, setRecipientPhone] = useState("");
  const [cardMessage, setCardMessage] = useState("");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(false);

  // Báo giá ship: đo quãng đường ở server, nhận token đã ký (dùng khi đặt hàng)
  const delivery = useQuery({
    queryKey: ["delivery-quote", pos?.lat, pos?.lng, date, lines],
    queryFn: () => api.deliveryQuote(pos!.lat, pos!.lng, lines, date),
    enabled: !!pos && lines.length > 0,
    retry: false,
    refetchInterval: 10 * 60_000, // token sống 15 phút -> làm mới trước khi hết hạn
  });
  const token = delivery.data?.quote_token;

  const slots = useQuery({ queryKey: ["slots", date], queryFn: () => api.slots(date) });
  useEffect(() => {
    setSlotId(null);
  }, [date]);

  const totals = useQuery({
    queryKey: ["checkout-quote", lines, token, date],
    queryFn: () => api.quoteCart(lines, token, date),
    enabled: lines.length > 0,
  });

  const days = useMemo(
    () =>
      Array.from({ length: (shop.data?.booking_window_days ?? 7) + 1 }, (_, i) => ({
        iso: vnDate(i),
        label: dayLabel(vnDate(i), i),
      })),
    [shop.data],
  );

  const errors = {
    pos: !pos ? "Bạn ghim vị trí nhận hoa trên bản đồ nhé." : null,
    address: address.trim().length < 5 ? "Nhập số nhà, tên đường, phường…" : null,
    slot: !slotId ? "Chọn một khung giờ giao." : null,
    name: name.trim() ? null : "Nhập tên người đặt.",
    phone: PHONE_RE.test(normalizePhone(phone)) ? null : "Số điện thoại di động chưa đúng.",
    recipientPhone:
      gift && recipientPhone && !PHONE_RE.test(normalizePhone(recipientPhone))
        ? "Số điện thoại người nhận chưa đúng."
        : null,
  };
  const valid = Object.values(errors).every((e) => !e) && !!token && !delivery.isFetching;

  const body = useMemo(
    () => ({
      items: lines,
      customer_name: name.trim(),
      customer_phone: normalizePhone(phone),
      recipient_name: gift && recipientName.trim() ? recipientName.trim() : null,
      recipient_phone: gift && recipientPhone ? normalizePhone(recipientPhone) : null,
      delivery_address: address.trim(),
      delivery_date: date,
      slot_id: slotId,
      card_message: cardMessage.trim() || null,
      note: note.trim() || null,
    }),
    [lines, name, phone, gift, recipientName, recipientPhone, address, date, slotId, cardMessage, note],
  );

  // Idempotency-Key: giữ nguyên khi bấm lại cùng nội dung (mạng chập chờn, bấm 2 lần) ->
  // server trả lại đúng đơn cũ; đổi nội dung đơn thì tạo khóa mới.
  const keyRef = useRef<{ body: string; key: string } | null>(null);
  const idempotencyKey = () => {
    const b = JSON.stringify(body);
    if (keyRef.current?.body !== b) keyRef.current = { body: b, key: crypto.randomUUID() };
    return keyRef.current.key;
  };

  const placeOrder = useMutation({
    mutationFn: async () => {
      const order = await api.createOrder(
        { ...body, delivery_quote_token: token },
        idempotencyKey(),
      );
      saveOrder({ code: order.code, token: order.tracking_token!, createdAt: order.created_at });
      cart.clear();
      try {
        const pay = await api.startPayment(order.tracking_token!);
        window.location.assign(pay.payment_url);
      } catch {
        navigate(`/don/${order.tracking_token}`);
      }
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code.includes("DELIVERY_QUOTE")) delivery.refetch();
      if (err instanceof ApiError && err.code.startsWith("SLOT_")) slots.refetch();
    },
  });

  if (lines.length === 0 && !placeOrder.isPending)
    return (
      <Empty icon="🧺" title="Giỏ hàng đang trống">
        <Link to="/" className="font-semibold text-rose-700">
          Chọn một bó hoa →
        </Link>
      </Empty>
    );
  if (shop.isPending) return <Loading />;
  if (shop.error) return <ErrorBox message={friendlyError(shop.error)} onRetry={() => shop.refetch()} />;

  const show = (e: string | null) => (touched ? e : null);
  const t = totals.data;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        setTouched(true);
        if (valid) placeOrder.mutate();
      }}
    >
      <h1 className="text-xl font-extrabold">Đặt hàng</h1>

      <Step n={1} title="Giao tới đâu?">
        <AddressMap
          shop={shop.data}
          value={pos}
          onChange={setPos}
          onAddressFound={(a) => setAddress(a)}
        />
        {show(errors.pos) && <p className="text-sm text-red-600">{errors.pos}</p>}
        {delivery.isFetching && <p className="text-sm text-stone-500">Đang tính phí ship…</p>}
        {delivery.error && <ErrorBox message={friendlyError(delivery.error)} />}
        {delivery.data && !delivery.isFetching && (
          <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-900">
            Cách shop ~{delivery.data.distance_km} km
            {delivery.data.provider === "haversine" && " (ước tính)"} · Phí ship{" "}
            <b>{delivery.data.free_shipping ? "Miễn phí 🎉" : money(delivery.data.fee)}</b>
            {delivery.data.holiday_surcharge > 0 && " (đã gồm phụ phí ngày lễ)"}
          </p>
        )}
        <Field label="Địa chỉ chi tiết" error={show(errors.address)}>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Số nhà, tên đường, phường, quận"
            className={inputCls}
            autoComplete="street-address"
          />
        </Field>
      </Step>

      <Step n={2} title="Giao lúc nào?">
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="radiogroup" aria-label="Ngày giao">
          {days.map((d) => (
            <button
              type="button"
              key={d.iso}
              role="radio"
              aria-checked={date === d.iso}
              onClick={() => setDate(d.iso)}
              className={`min-h-11 shrink-0 rounded-xl px-4 text-sm font-semibold ring-1 ${date === d.iso ? "bg-rose-600 text-white ring-rose-600" : "bg-white text-stone-700 ring-stone-200"}`}
            >
              {d.label}
            </button>
          ))}
        </div>
        {slots.isPending && <Loading text="Đang xem khung giờ…" />}
        {slots.data && (
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Khung giờ">
            {slots.data.map((s) => (
              <button
                type="button"
                key={s.slot_id}
                role="radio"
                aria-checked={slotId === s.slot_id}
                disabled={!s.bookable}
                onClick={() => setSlotId(s.slot_id)}
                className={`min-h-14 rounded-xl px-3 py-2 text-left ring-1 disabled:opacity-40 ${slotId === s.slot_id ? "bg-rose-600 text-white ring-rose-600" : "bg-white ring-stone-200"}`}
              >
                <span className="block font-semibold">
                  {s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}
                </span>
                <span className="block text-xs opacity-80">
                  {s.bookable
                    ? s.remaining <= 2
                      ? `Còn ${s.remaining} chỗ`
                      : "Còn chỗ"
                    : { FULL: "Kín chỗ", CLOSED: "Nghỉ", TOO_LATE: "Không kịp", OUT_OF_WINDOW: "—" }[
                        s.reason ?? "FULL"
                      ]}
                </span>
              </button>
            ))}
          </div>
        )}
        {show(errors.slot) && <p className="text-sm text-red-600">{errors.slot}</p>}
      </Step>

      <Step n={3} title="Thông tin người đặt">
        <Field label="Họ tên" error={show(errors.name)}>
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} autoComplete="name" />
        </Field>
        <Field label="Số điện thoại" error={show(errors.phone)}>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className={inputCls}
            inputMode="tel"
            autoComplete="tel"
            placeholder="09xx xxx xxx"
          />
        </Field>
        <label className="flex min-h-11 items-center gap-3">
          <input type="checkbox" checked={gift} onChange={(e) => setGift(e.target.checked)} className="size-5 accent-rose-600" />
          <span>Tặng người khác</span>
        </label>
        {gift && (
          <div className="space-y-3 rounded-xl bg-rose-50/60 p-3">
            <Field label="Tên người nhận">
              <input value={recipientName} onChange={(e) => setRecipientName(e.target.value)} className={inputCls} />
            </Field>
            <Field label="SĐT người nhận (để shipper gọi)" error={show(errors.recipientPhone)}>
              <input value={recipientPhone} onChange={(e) => setRecipientPhone(e.target.value)} className={inputCls} inputMode="tel" />
            </Field>
            <Field label={`Lời nhắn trên thiệp (${cardMessage.length}/300)`}>
              <textarea
                value={cardMessage}
                onChange={(e) => setCardMessage(e.target.value.slice(0, 300))}
                rows={3}
                className={`${inputCls} py-2`}
              />
            </Field>
          </div>
        )}
        <Field label="Ghi chú cho shop (không bắt buộc)">
          <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 500))} className={inputCls} />
        </Field>
      </Step>

      {t && (
        <dl className="space-y-1 rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-100">
          {t.lines.map((l) => (
            <div key={l.template_id} className="flex justify-between">
              <dt>
                {l.name} × {l.quantity}
              </dt>
              <dd className="tabular-nums">{money(l.line_total)}</dd>
            </div>
          ))}
          {t.discount_total > 0 && (
            <div className="flex justify-between text-rose-700">
              <dt>Đã gồm ưu đãi hoa tươi</dt>
              <dd className="tabular-nums">−{money(t.discount_total)}</dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt>Phí giao hàng</dt>
            <dd className="tabular-nums">
              {t.delivery_fee == null ? "—" : t.delivery_fee === 0 ? "Miễn phí" : money(t.delivery_fee)}
            </dd>
          </div>
        </dl>
      )}

      {placeOrder.error && <ErrorBox message={friendlyError(placeOrder.error)} />}
      <p className="text-center text-xs text-stone-500">
        Sau khi đặt, shop giữ hoa và khung giờ cho bạn trong {shop.data.hold_minutes} phút để thanh toán.
      </p>

      <BottomBar>
        <div className="flex-1">
          <p className="text-xs text-stone-500">Tổng thanh toán</p>
          <p className="text-lg font-extrabold tabular-nums">
            {t && t.delivery_fee != null ? money(t.total) : "—"}
          </p>
        </div>
        <Button type="submit" className="flex-1" loading={placeOrder.isPending} disabled={touched && !valid}>
          Đặt & thanh toán
        </Button>
      </BottomBar>
    </form>
  );
}
