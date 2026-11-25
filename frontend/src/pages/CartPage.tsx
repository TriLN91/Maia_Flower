import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import { BottomBar, Button, Empty, ErrorBox, Loading, Stepper } from "../components/ui";
import { cart, useCart } from "../lib/cart";
import { friendlyError } from "../lib/errors";
import { money } from "../lib/format";

export function CartPage() {
  const lines = useCart();
  const navigate = useNavigate();
  const quote = useQuery({
    queryKey: ["cart-quote", lines],
    queryFn: () => api.quoteCart(lines),
    enabled: lines.length > 0,
    placeholderData: keepPreviousData,
  });

  if (lines.length === 0)
    return (
      <Empty icon="🧺" title="Giỏ hàng đang trống">
        <Link to="/" className="font-semibold text-rose-700">
          Chọn một bó hoa →
        </Link>
      </Empty>
    );

  const q = quote.data;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Giỏ hàng</h1>
      {quote.isPending && <Loading text="Đang tính giá…" />}
      {quote.error && (
        <ErrorBox message={friendlyError(quote.error)} onRetry={() => quote.refetch()} />
      )}

      {q && (
        <>
          <ul className="space-y-3">
            {q.lines.map((l) => (
              <li key={l.template_id} className="rounded-2xl bg-white p-4 ring-1 ring-stone-100">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold">{l.name}</p>
                    <p className="text-sm text-stone-500">
                      {money(l.unit_price)}
                      {l.discount_pct > 0 && (
                        <span className="ml-1 font-semibold text-rose-600">−{l.discount_pct}%</span>
                      )}
                    </p>
                  </div>
                  <p className="font-bold tabular-nums">{money(l.line_total)}</p>
                </div>
                {!l.available && (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    Hiện không đủ hoa tươi cho số lượng này — thử giảm số bó nhé.
                  </p>
                )}
                <div className="mt-3 flex items-center justify-between">
                  <Stepper
                    value={l.quantity}
                    onChange={(v) => cart.set(l.template_id, v)}
                    label={`Số lượng ${l.name}`}
                  />
                  <button
                    className="min-h-11 px-2 text-sm text-stone-500 hover:text-red-600"
                    onClick={() => cart.set(l.template_id, 0)}
                  >
                    Xóa
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <dl className="space-y-1 rounded-2xl bg-white p-4 text-sm ring-1 ring-stone-100">
            <div className="flex justify-between">
              <dt>Tạm tính</dt>
              <dd className="tabular-nums">{money(q.subtotal)}</dd>
            </div>
            {q.discount_total > 0 && (
              <div className="flex justify-between text-rose-700">
                <dt>Ưu đãi hoa tươi</dt>
                <dd className="tabular-nums">−{money(q.discount_total)}</dd>
              </div>
            )}
            <div className="flex justify-between text-stone-500">
              <dt>Phí giao hàng</dt>
              <dd>tính ở bước sau</dd>
            </div>
          </dl>

          <BottomBar>
            <div className="flex-1">
              <p className="text-xs text-stone-500">Tổng (chưa gồm ship)</p>
              <p className="text-lg font-extrabold tabular-nums">{money(q.total)}</p>
            </div>
            <Button
              className="flex-1"
              disabled={!q.all_available || quote.isFetching}
              onClick={() => navigate("/dat-hang")}
            >
              Đặt hàng →
            </Button>
          </BottomBar>
        </>
      )}
    </div>
  );
}
