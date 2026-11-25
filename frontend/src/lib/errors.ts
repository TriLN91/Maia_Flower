import { ApiError } from "../api/client";

/** Đổi mã lỗi backend thành câu tiếng Việt cho khách. Dựa vào `code`, không đọc `detail`. */
export function friendlyError(err: unknown): string {
  if (!(err instanceof ApiError)) return "Không kết nối được tới cửa hàng. Bạn kiểm tra mạng nhé.";
  const x = err.extra;
  switch (err.code) {
    case "OUT_OF_STOCK": {
      const items = (x.shortages as { name: string; needed: number; available: number }[]) ?? [];
      const list = items.map((s) => `${s.name} (cần ${s.needed}, còn ${s.available})`).join(", ");
      return `Rất tiếc, shop vừa hết hoa tươi cho đơn này: ${list}. Bạn bớt số lượng hoặc chọn mẫu khác nhé.`;
    }
    case "TEMPLATE_UNAVAILABLE":
      return "Có mẫu trong giỏ đã ngừng bán. Bạn xóa mẫu đó khỏi giỏ giúp shop nhé.";
    case "SLOT_FULL":
      return "Khung giờ này vừa kín chỗ. Bạn chọn khung giờ khác nhé.";
    case "SLOT_TOO_LATE":
      return "Khung giờ này quá gần, shop không kịp bó hoa. Bạn chọn khung muộn hơn nhé.";
    case "SLOT_OUT_OF_WINDOW":
    case "SLOT_CLOSED":
      return "Khung giờ này không nhận đơn. Bạn chọn ngày/giờ khác nhé.";
    case "OUT_OF_DELIVERY_RANGE":
      return `Địa chỉ cách shop khoảng ${x.distance_km} km — ngoài vùng giao (tối đa ${x.max_km} km).`;
    case "DELIVERY_QUOTE_EXPIRED":
    case "INVALID_DELIVERY_QUOTE":
      return "Báo giá ship đã hết hạn. Bạn chọn lại vị trí giao hàng nhé.";
    case "HOLD_EXPIRED":
      return "Đã quá 15 phút giữ hoa. Bạn đặt lại đơn mới nhé.";
    case "ORDER_NOT_PAYABLE":
      return "Đơn này không còn chờ thanh toán.";
    case "RATE_LIMITED":
      return `Bạn thao tác hơi nhanh, thử lại sau ${x.retry_after ?? 30} giây nhé.`;
    case "ADDRESS_SEARCH_UNAVAILABLE":
      return "Tìm địa chỉ đang tạm tắt — bạn ghim vị trí trên bản đồ nhé.";
    case "VALIDATION_ERROR":
      return "Thông tin chưa hợp lệ, bạn kiểm tra lại các ô nhé.";
    case "NOT_FOUND":
      return "Không tìm thấy thông tin.";
    default:
      return "Có lỗi xảy ra, bạn thử lại sau ít phút nhé.";
  }
}
