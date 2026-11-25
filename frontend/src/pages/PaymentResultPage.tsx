import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import { ErrorBox, Loading } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { tokenForCode } from "../lib/orders";

/** Cổng thanh toán redirect về đây kèm tham số đã ký. Trang chỉ HIỂN THỊ: trạng thái thật do
 * IPN (server-to-server) cập nhật — backend đọc từ DB, không tin tham số trên URL. */
export function PaymentResultPage() {
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

  if (result.isPending) return <Loading text="Đang xác nhận thanh toán…" />;
  if (result.error) return <ErrorBox message={friendlyError(result.error)} />;

  const r = result.data;
  const ok = r.order_status === "paid";
  const token = tokenForCode(r.order_code);

  return (
    <div className="space-y-5 py-8 text-center">
      <div className="text-6xl">{ok ? "💐" : r.gateway_success ? "⏳" : "😕"}</div>
      <h1 className="text-xl font-extrabold">
        {ok ? "Thanh toán thành công!" : r.gateway_success ? "Đang xác nhận…" : "Chưa thanh toán được"}
      </h1>
      <p className="text-stone-600">{r.message}</p>
      <p className="font-mono text-sm text-stone-500">Mã đơn: {r.order_code}</p>
      {token ? (
        <Link
          to={`/don/${token}`}
          className="inline-flex min-h-11 items-center rounded-xl bg-rose-600 px-5 font-semibold text-white"
        >
          {ok ? "Theo dõi đơn hàng" : "Xem đơn / thử thanh toán lại"}
        </Link>
      ) : (
        <Link to="/" className="font-semibold text-rose-700">
          Về trang chủ
        </Link>
      )}
    </div>
  );
}
