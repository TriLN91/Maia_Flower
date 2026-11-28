import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { Template } from "../api/types";
import { BouquetArt } from "../components/BouquetArt";
import { ArrowRightIcon, BagIcon, ShieldIcon, TrashIcon, TruckIcon } from "../components/icons";
import { BottomBar, Button, Empty, ErrorBox, Loading, Stepper } from "../components/ui";
import { cart, useCart } from "../lib/cart";
import { friendlyError } from "../lib/errors";
import { useTitle } from "../lib/title";
import { money } from "../lib/format";

/** Thanh tiến độ "còn X nữa để được miễn phí ship" — một mẫu tăng giá trị đơn rất phổ biến. */
function FreeShipProgress({ subtotal }: { subtotal: number }) {
  const shop = useQuery({ queryKey: ["shop-info"], queryFn: api.shopInfo, staleTime: 300_000 });
  const min = shop.data?.free_ship_min_subtotal;
  if (!min) return null;
  const left = Math.max(0, min - subtotal);
  const pct = Math.min(100, (subtotal / min) * 100);
  return (
    <div className="rounded-2xl bg-sage-50 p-4 text-sm text-sage-800 ring-1 ring-sage-100">
      <p className="flex items-center gap-2">
        <TruckIcon className="text-sage-700" />
        {left > 0 ? (
          <span>
            Mua thêm <b>{money(left)}</b> để được miễn phí giao hàng (trong {shop.data!.free_ship_max_km} km)
          </span>
        ) : (
          <span>
            <b>Đơn của bạn được miễn phí giao hàng</b> (trong {shop.data!.free_ship_max_km} km)
          </span>
        )}
      </p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white" aria-hidden>
        <div className="h-full rounded-full bg-sage-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function CartPage() {
  useTitle("Giỏ hàng");
  const lines = useCart();
  const navigate = useNavigate();
  const quote = useQuery({
    queryKey: ["cart-quote", lines],
    queryFn: () => api.quoteCart(lines),
    enabled: lines.length > 0,
    placeholderData: keepPreviousData,
  });
  const catalog = useQuery({ queryKey: ["templates", "name"], queryFn: () => api.templates("name") });
  const byId = new Map<number, Template>((catalog.data?.items ?? []).map((t) => [t.id, t]));

  if (lines.length === 0)
    return (
      <Empty icon={<BagIcon className="size-9" />} title="Giỏ hàng đang trống">
        <p>Chọn một bó hoa thật xinh để bắt đầu nhé.</p>
        <Link
          to="/"
          className="mt-5 inline-flex min-h-12 items-center gap-2 rounded-full bg-brand-700 px-6 font-semibold text-white"
        >
          Xem các mẫu hoa <ArrowRightIcon className="size-4" />
        </Link>
      </Empty>
    );

  const q = quote.data;
  const checkout = (
    <Button
      className="flex-1 lg:w-full"
      disabled={!q?.all_available || quote.isFetching}
      onClick={() => navigate("/dat-hang")}
    >
      <span className="whitespace-nowrap">
        <span className="sm:hidden">Đặt hàng</span>
        <span className="hidden sm:inline">Tiến hành đặt hàng</span>
      </span>
      <ArrowRightIcon className="size-4" />
    </Button>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-ink sm:text-4xl">Giỏ hàng</h1>
        <p className="mt-1 text-sm text-stone-500">{lines.reduce((n, l) => n + l.quantity, 0)} bó hoa</p>
      </div>
      {quote.isPending && <Loading text="Đang tính giá…" />}
      {quote.error && <ErrorBox message={friendlyError(quote.error)} onRetry={() => quote.refetch()} />}

      {q && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
          <ul className="space-y-3">
            {q.lines.map((l) => {
              const t = byId.get(l.template_id);
              return (
                <li key={l.template_id} className="flex gap-4 rounded-3xl bg-white p-3 ring-1 ring-stone-200/70 sm:p-4">
                  <Link to={t ? `/mau/${t.slug}` : "#"} className="w-24 shrink-0 overflow-hidden rounded-2xl bg-paper sm:w-28">
                    {t ? <BouquetArt template={t} /> : <div className="aspect-[4/5]" />}
                  </Link>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-display text-lg font-semibold leading-snug text-ink">{l.name}</p>
                        <p className="text-sm text-stone-500">
                          {money(l.unit_price)} / bó
                          {l.discount_pct > 0 && (
                            <span className="ml-1.5 rounded-full bg-brand-50 px-1.5 py-0.5 text-xs font-semibold text-brand-700">
                              −{l.discount_pct}%
                            </span>
                          )}
                        </p>
                      </div>
                      <button
                        className="-mr-1 -mt-1 flex size-10 shrink-0 items-center justify-center rounded-full text-stone-400 hover:bg-red-50 hover:text-red-600"
                        onClick={() => cart.set(l.template_id, 0)}
                        aria-label={`Xóa ${l.name} khỏi giỏ`}
                      >
                        <TrashIcon className="size-[18px]" />
                      </button>
                    </div>
                    {!l.available && (
                      <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        Hiện không đủ hoa tươi cho số lượng này, bạn thử giảm số bó nhé.
                      </p>
                    )}
                    <div className="mt-auto flex items-center justify-between gap-2 pt-3">
                      <Stepper value={l.quantity} onChange={(v) => cart.set(l.template_id, v)} label={`Số lượng ${l.name}`} />
                      <p className="font-bold tabular-nums text-ink">{money(l.line_total)}</p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <aside className="space-y-3 lg:sticky lg:top-24">
            <FreeShipProgress subtotal={q.total} />
            <div className="space-y-4 rounded-3xl bg-white p-5 ring-1 ring-stone-200/70">
              <h2 className="font-display text-xl font-semibold text-ink">Tóm tắt đơn</h2>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-stone-500">Tạm tính</dt>
                  <dd className="tabular-nums">{money(q.subtotal)}</dd>
                </div>
                {q.discount_total > 0 && (
                  <div className="flex justify-between text-brand-700">
                    <dt>Ưu đãi hoa tươi</dt>
                    <dd className="tabular-nums">−{money(q.discount_total)}</dd>
                  </div>
                )}
                <div className="flex justify-between">
                  <dt className="text-stone-500">Phí giao hàng</dt>
                  <dd className="text-stone-500">Tính ở bước sau</dd>
                </div>
                <div className="flex justify-between border-t border-stone-100 pt-3 text-base font-bold">
                  <dt>Tổng</dt>
                  <dd className="tabular-nums">{money(q.total)}</dd>
                </div>
              </dl>
              <div className="hidden lg:block">{checkout}</div>
              <p className="flex items-center gap-2 text-xs text-stone-500">
                <ShieldIcon className="size-4 text-sage-700" /> Hoa được giữ 15 phút khi bạn thanh toán
              </p>
            </div>
            <Link to="/" className="block py-2 text-center text-sm font-semibold text-brand-700">
              ← Tiếp tục chọn hoa
            </Link>
          </aside>

          <BottomBar desktopHidden>
            <div className="flex-1">
              <p className="text-xs text-stone-500">Tổng (chưa gồm ship)</p>
              <p className="text-lg font-bold tabular-nums">{money(q.total)}</p>
            </div>
            {checkout}
          </BottomBar>
        </div>
      )}
    </div>
  );
}
