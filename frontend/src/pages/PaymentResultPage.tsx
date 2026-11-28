import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import { CheckIcon, ClockIcon, PinIcon } from "../components/icons";
import { OrderItems } from "../components/OrderItems";
import { ErrorBox, Loading } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { timeRange } from "../lib/format";
import { tokenForCode } from "../lib/orders";
import { useTitle } from "../lib/title";

/** Cổng thanh toán redirect về đây kèm tham số đã ký. Trang chỉ HIỂN THỊ: trạng thái thật do
 * IPN (server-to-server) cập nhật — backend đọc từ DB, không tin tham số trên URL. */
export function PaymentResultPage() {
  useTitle("Kết quả thanh toán");
  const [params] = useSearchParams();
  const query = params.toString();
  const result = useQuery({
    queryKey: ["payment-return", query],
    queryFn: () => api.paymentReturn(query),
    // Cổng báo thành công nhưng IPN chưa tới -> hỏi lại vài lần
    refetchInterval: (q) =>
      q.state.data && q.state.data.gateway_success && q.state.data.order_status === "pending_payment"
        ? 2000
        : false,
  });

  const token = result.data ? tokenForCode(result.data.order_code) : undefined;
  const order = useQuery({
    queryKey: ["order", token],
    queryFn: () => api.track(token!),
    enabled: !!token,
  });

  if (result.isPending) return <Loading text="Đang xác nhận thanh toán…" />;
  if (result.error) return <ErrorBox message={friendlyError(result.error)} />;

  const r = result.data;
  const ok = r.order_status === "paid";

  return (
    <div className="mx-auto max-w-md space-y-5 py-10 text-center">
      <div
        className={`mx-auto flex size-20 items-center justify-center rounded-full ${ok ? "bg-sage-50 text-sage-700" : r.gateway_success ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-600"}`}
      >
        {ok ? <CheckIcon className="size-10" /> : r.gateway_success ? <ClockIcon className="size-10" /> : <span className="text-3xl font-bold">!</span>}
      </div>
      <h1 className="font-display text-3xl font-semibold text-ink">
        {ok ? "Cảm ơn bạn đã đặt hoa!" : r.gateway_success ? "Đang xác nhận…" : "Chưa thanh toán được"}
      </h1>
      <p className="text-stone-600">{r.message}</p>
      {ok && <p className="text-sm text-stone-500">Thợ Maia sẽ bắt đầu bó hoa cho bạn ngay.</p>}
      <p className="inline-block rounded-full bg-white px-4 py-1.5 text-sm text-stone-600 ring-1 ring-stone-200">
        Mã đơn <b className="text-ink">{r.order_code}</b>
      </p>
      <div>
        {token ? (
          <Link
            to={`/don/${token}`}
            className="inline-flex min-h-12 items-center rounded-full bg-brand-700 px-6 font-semibold text-white hover:bg-brand-800"
          >
            {ok ? "Theo dõi đơn hàng" : "Xem đơn / thử thanh toán lại"}
          </Link>
        ) : (
          <Link to="/" className="font-semibold text-brand-700">
            Về trang chủ
          </Link>
        )}
      </div>

      {order.data && (
        <section className="space-y-4 rounded-3xl bg-white p-5 text-left ring-1 ring-stone-200/70">
          <div className="space-y-2 text-sm">
            <p className="flex gap-3">
              <ClockIcon className="text-sage-700" />
              <span>
                <span className="block text-xs text-stone-500">Giao lúc</span>
                <b className="text-ink">{timeRange(order.data.delivery_starts_at, order.data.delivery_ends_at)}</b>
              </span>
            </p>
            <p className="flex gap-3">
              <PinIcon className="text-sage-700" />
              <span>
                <span className="block text-xs text-stone-500">Giao tới</span>
                {order.data.delivery_address}
              </span>
            </p>
          </div>
          <div className="border-t border-stone-100 pt-4">
            <OrderItems order={order.data} />
          </div>
        </section>
      )}
    </div>
  );
}
