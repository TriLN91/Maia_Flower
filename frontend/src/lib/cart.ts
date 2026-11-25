import { useSyncExternalStore } from "react";
import type { CartLine } from "../api/types";

/**
 * Giỏ hàng lưu ở localStorage (khách không cần đăng nhập). Chỉ lưu id + số lượng;
 * giá luôn do server tính lại (/shop/cart/quote), không tin giá ở trình duyệt.
 */
const KEY = "maia.cart.v1";
const listeners = new Set<() => void>();
let cache: CartLine[] = read();

function read(): CartLine[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw)
      ? raw.filter((l) => Number.isInteger(l.template_id) && l.quantity > 0)
      : [];
  } catch {
    return [];
  }
}

function write(lines: CartLine[]) {
  cache = lines;
  localStorage.setItem(KEY, JSON.stringify(lines));
  listeners.forEach((fn) => fn());
}

// Đồng bộ giữa các tab
window.addEventListener("storage", (e) => {
  if (e.key === KEY) {
    cache = read();
    listeners.forEach((fn) => fn());
  }
});

export const MAX_PER_LINE = 20;

export const cart = {
  get: () => cache,
  add(templateId: number, quantity = 1) {
    const existing = cache.find((l) => l.template_id === templateId);
    if (existing) {
      cart.set(templateId, existing.quantity + quantity);
    } else {
      write([...cache, { template_id: templateId, quantity: Math.min(quantity, MAX_PER_LINE) }]);
    }
  },
  set(templateId: number, quantity: number) {
    const q = Math.max(0, Math.min(quantity, MAX_PER_LINE));
    write(
      q === 0
        ? cache.filter((l) => l.template_id !== templateId)
        : cache.map((l) => (l.template_id === templateId ? { ...l, quantity: q } : l)),
    );
  },
  clear: () => write([]),
};

export function useCart(): CartLine[] {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => cache,
  );
}

export const cartCount = (lines: CartLine[]) => lines.reduce((n, l) => n + l.quantity, 0);
