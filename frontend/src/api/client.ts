import type {
  CartLine,
  CartQuote,
  DeliveryQuote,
  Order,
  Page,
  PaymentReturn,
  PaymentStart,
  PlaceSuggestion,
  ShopInfo,
  Slot,
  Template,
} from "./types";

/** Lỗi nghiệp vụ từ backend: {"detail", "code", "extra"} (xem app/core/errors.py). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (res.ok) return (res.status === 204 ? undefined : await res.json()) as T;

  let body: { detail?: unknown; code?: string; extra?: Record<string, unknown> } = {};
  try {
    body = await res.json();
  } catch {
    /* không phải JSON */
  }
  const code = body.code ?? (res.status === 422 ? "VALIDATION_ERROR" : `HTTP_${res.status}`);
  const detail = typeof body.detail === "string" ? body.detail : res.statusText;
  throw new ApiError(res.status, code, detail, body.extra ?? {});
}

const post = <T>(path: string, body: unknown, headers?: Record<string, string>) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body), headers });

export const api = {
  shopInfo: () => request<ShopInfo>("/shop/info"),
  templates: (sort = "name") => request<Page<Template>>(`/shop/templates?limit=50&sort=${sort}`),
  freshToday: () => request<Template[]>("/shop/templates/fresh-today"),
  template: (slug: string) => request<Template>(`/shop/templates/${encodeURIComponent(slug)}`),

  quoteCart: (items: CartLine[], deliveryQuoteToken?: string, deliveryDate?: string) =>
    post<CartQuote>("/shop/cart/quote", {
      items,
      delivery_quote_token: deliveryQuoteToken,
      delivery_date: deliveryDate,
    }),
  deliveryQuote: (lat: number, lng: number, items: CartLine[], deliveryDate?: string) =>
    post<DeliveryQuote>("/shop/delivery/quote", { lat, lng, items, delivery_date: deliveryDate }),
  slots: (date: string) => request<Slot[]>(`/shop/delivery-slots?date=${date}`),
  autocomplete: (q: string) =>
    request<PlaceSuggestion[]>(`/shop/address/autocomplete?q=${encodeURIComponent(q)}`),
  place: (placeId: string) =>
    request<{ address: string; lat: number; lng: number }>(
      `/shop/address/place/${encodeURIComponent(placeId)}`,
    ),

  createOrder: (body: Record<string, unknown>, idempotencyKey: string) =>
    post<Order>("/shop/orders", body, { "Idempotency-Key": idempotencyKey }),
  track: (token: string) => request<Order>(`/shop/orders/track/${encodeURIComponent(token)}`),
  startPayment: (token: string) =>
    post<PaymentStart>(`/shop/orders/track/${encodeURIComponent(token)}/pay`, {}),
  paymentReturn: (query: string) => request<PaymentReturn>(`/payments/mock/return?${query}`),
};
