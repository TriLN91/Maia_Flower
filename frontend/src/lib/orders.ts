/** Danh sách đơn đã đặt trên máy này (khách không có tài khoản -> nhớ tracking token cục bộ). */
const KEY = "maia.orders.v1";

export interface SavedOrder {
  code: string;
  token: string;
  createdAt: string;
}

export function savedOrders(): SavedOrder[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

export function saveOrder(order: SavedOrder) {
  const rest = savedOrders().filter((o) => o.code !== order.code);
  localStorage.setItem(KEY, JSON.stringify([order, ...rest].slice(0, 30)));
}

export const tokenForCode = (code: string) => savedOrders().find((o) => o.code === code)?.token;
