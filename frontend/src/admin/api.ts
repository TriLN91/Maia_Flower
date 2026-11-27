import { useSyncExternalStore } from "react";
import { apiUrl } from "../api/base";
import { ApiError } from "../api/client";
import type { OrderStatus } from "../api/types";

// ---------------- Phiên đăng nhập (JWT trong sessionStorage: đóng tab là đăng xuất)
const KEY = "maia.admin.session";
export interface Session {
  token: string;
  expiresAt: number;
  email: string;
  fullName: string;
  role: "staff" | "owner";
}
const listeners = new Set<() => void>();
let current: Session | null = load();

function load(): Session | null {
  try {
    const s = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as Session | null;
    return s && s.expiresAt > Date.now() ? s : null;
  } catch {
    return null;
  }
}
function setSession(s: Session | null) {
  current = s;
  if (s) sessionStorage.setItem(KEY, JSON.stringify(s));
  else sessionStorage.removeItem(KEY);
  listeners.forEach((fn) => fn());
}
export const logout = () => setSession(null);
export function useSession() {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    () => current,
  );
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (current && current.expiresAt <= Date.now()) logout();
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(current ? { Authorization: `Bearer ${current.token}` } : {}),
      ...init.headers,
    },
  });
  if (res.status === 401 && current) logout(); // token hết hạn / tài khoản bị khóa
  if (res.ok) return (res.status === 204 ? undefined : await res.json()) as T;
  let body: { detail?: unknown; code?: string; extra?: Record<string, unknown> } = {};
  try {
    body = await res.json();
  } catch {
    /* empty */
  }
  throw new ApiError(
    res.status,
    body.code ?? (res.status === 422 ? "VALIDATION_ERROR" : `HTTP_${res.status}`),
    typeof body.detail === "string" ? body.detail : res.statusText,
    body.extra ?? {},
  );
}
const send = <T>(method: string, path: string, body?: unknown) =>
  call<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export async function login(email: string, password: string) {
  const res = await fetch(apiUrl("/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.code ?? `HTTP_${res.status}`, body.detail ?? "", body.extra);
  }
  const { access_token, expires_in } = await res.json();
  current = { token: access_token, expiresAt: Date.now() + expires_in * 1000 } as Session;
  const me = await call<{ email: string; full_name: string; role: "staff" | "owner" }>("/auth/me");
  setSession({
    token: access_token,
    expiresAt: Date.now() + expires_in * 1000 - 30_000,
    email: me.email,
    fullName: me.full_name,
    role: me.role,
  });
}

// ---------------- Kiểu dữ liệu admin
export interface FlowerType {
  id: number;
  name: string;
  color: string;
  reference_cost: number;
  vase_life_days: number;
  is_active: boolean;
}
export interface Supplier {
  id: number;
  name: string;
  phone: string | null;
  is_active: boolean;
}
export interface Batch {
  id: number;
  flower_type: { id: number; name: string; color: string };
  supplier: { id: number; name: string };
  quantity_received: number;
  quantity_available: number;
  cost_per_stem: number;
  received_at: string;
  expected_expiry_at: string;
  status: "active" | "needs_review" | "depleted" | "discarded";
  freshness: number;
  days_left: number;
  is_sellable: boolean;
}
export interface FlowerStock {
  flower_type: { id: number; name: string; color: string };
  total_available: number;
  sellable: number;
  expiring_soon: number;
  avg_freshness: number | null;
  nearest_expiry_at: string | null;
  batch_count: number;
}
export interface OrderSummary {
  id: number;
  code: string;
  status: OrderStatus;
  customer_name: string;
  delivery_starts_at: string;
  delivery_ends_at: string;
  total: number;
  item_count: number;
}
export interface AdminOrder {
  id: number;
  code: string;
  status: OrderStatus;
  customer_name: string;
  customer_phone: string;
  recipient_name: string | null;
  recipient_phone: string | null;
  delivery_address: string;
  delivery_starts_at: string;
  delivery_ends_at: string;
  card_message: string | null;
  note: string | null;
  items: {
    template_id: number;
    template_name: string;
    quantity: number;
    line_total: number;
    discount_pct: number;
    allocations: { batch_id: number; flower_type_id: number; quantity: number }[];
  }[];
  total: number;
  delivery_fee: number;
  events: { from_status: OrderStatus | null; to_status: OrderStatus; actor: string; note: string | null; created_at: string }[];
  payments: { txn_ref: string; status: string; amount: number; needs_refund: boolean; paid_at: string | null }[];
}
export interface AdminTemplate {
  id: number;
  name: string;
  slug: string;
  price: number;
  is_active: boolean;
  discount_locked: boolean;
  current_discount_pct: number;
  items: { flower_type: { id: number; name: string }; quantity: number }[];
}
export interface TemplateCost {
  price: number;
  cost: number;
  margin_pct: number | null;
  price_floor: number;
  lowest_price_after_discount: number;
  warnings: string[];
}
export interface Urgency {
  flower_type_id: number;
  name: string;
  expiring_qty: number;
  expected_demand: number;
  surplus: number;
  min_days_left: number | null;
  avg_freshness: number | null;
  discount_pct: number;
  computed_at: string;
}
export interface DiscountLog {
  old_pct: number;
  new_pct: number;
  created_at: string;
  reason: { target_pct: number; limits: string[]; flowers: { name: string; surplus: number }[] };
}
export interface FlowerForecast {
  flower_type_id: number;
  name: string;
  total: number;
  days: { target_date: string; predicted_qty: number; base_qty: number; multiplier: number; holiday: string | null }[];
}
export interface Restock {
  flower_type_id: number;
  name: string;
  cover_days: number;
  forecast_total: number;
  usable_stock: number;
  suggested_qty: number;
  est_cost: number;
  holidays: string[];
}
export interface Score {
  wape: number | null;
  mape: number | null;
  points: number;
}
export interface Backtest {
  origins: number;
  horizon: number;
  model: Score;
  naive_last_week: Score;
  moving_avg_14: Score;
  improvement_vs_moving_avg_pct: number | null;
  per_flower: { name: string; wape: number }[];
}
export interface PricingSettings {
  enabled: boolean;
  horizon_days: number;
  tiers: { days_left_max: number; pct: number }[];
  max_discount_pct: number;
  min_margin_pct: number;
  max_step_pct: number;
  demand_lookback_days: number;
  min_surplus_stems: number;
}
export interface SlotDay {
  slot_id: number;
  date: string;
  start_time: string;
  end_time: string;
  capacity: number;
  reserved_count: number;
  is_closed: boolean;
  overridden: boolean;
}

// ---------------- Gọi API
const q = (params: Record<string, string | number | undefined>) =>
  new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
  ).toString();

export const admin = {
  orders: (p: { status?: string; delivery_date?: string }) =>
    call<{ items: OrderSummary[]; total: number }>(`/admin/orders?${q({ ...p, limit: 100 })}`),
  order: (id: number) => call<AdminOrder>(`/admin/orders/${id}`),
  transition: (id: number, to_status: OrderStatus, note?: string) =>
    send<AdminOrder>("POST", `/admin/orders/${id}/transition`, { to_status, note }),

  flowerTypes: () => call<FlowerType[]>("/admin/flower-types"),
  suppliers: () => call<Supplier[]>("/admin/suppliers"),
  inventory: () => call<FlowerStock[]>("/admin/inventory"),
  batches: (p: { flower_type_id?: number; status?: string }) => call<Batch[]>(`/admin/batches?${q(p)}`),
  importBatch: (b: { flower_type_id: number; supplier_id: number; quantity: number; cost_per_stem: number }) =>
    send<Batch>("POST", "/admin/batches", b),
  waste: (id: number, quantity: number, reason: string) =>
    send<Batch>("POST", `/admin/batches/${id}/waste`, { quantity, reason }),
  discard: (id: number, reason: string) => send<Batch>("POST", `/admin/batches/${id}/discard`, { reason }),

  templates: () => call<AdminTemplate[]>("/admin/templates"),
  updateTemplate: (id: number, body: Partial<{ price: number; is_active: boolean; discount_locked: boolean }>) =>
    send<AdminTemplate>("PATCH", `/admin/templates/${id}`, body),
  templateCost: (id: number) => call<TemplateCost>(`/admin/templates/${id}/cost`),
  discountLog: (id: number) => call<DiscountLog[]>(`/admin/templates/${id}/discount-log`),
  urgency: () => call<Urgency[]>("/admin/urgency"),
  recomputePricing: () => send<{ templates_changed: number }>("POST", "/admin/pricing/recompute"),
  pricingSettings: () => call<PricingSettings>("/admin/settings/pricing"),
  savePricingSettings: (s: PricingSettings) => send<PricingSettings>("PUT", "/admin/settings/pricing", s),

  forecast: () => call<FlowerForecast[]>("/admin/forecast"),
  recomputeForecast: () => send<{ rows: number }>("POST", "/admin/forecast/recompute"),
  restock: () => call<Restock[]>("/admin/restock-suggestions"),
  backtest: () => call<Backtest>("/admin/forecast/backtest"),

  slotDays: (date: string) => call<SlotDay[]>(`/admin/delivery-slot-days?date=${date}`),
  overrideSlotDay: (slotId: number, date: string, body: { capacity?: number; is_closed?: boolean }) =>
    send<SlotDay>("PUT", `/admin/delivery-slots/${slotId}/days/${date}`, body),
  audit: () => call<{ ok: boolean; batches_checked: number }>("/admin/inventory/audit"),
};

/** Bước chuyển trạng thái hợp lệ — khớp STAFF_TRANSITIONS ở backend (order_workflow.py). */
export const TRANSITIONS: { from: OrderStatus; to: OrderStatus; label: string; ownerOnly?: boolean; danger?: boolean }[] = [
  { from: "paid", to: "preparing", label: "Bắt đầu bó" },
  { from: "preparing", to: "delivering", label: "Giao cho shipper" },
  { from: "delivering", to: "completed", label: "Đã giao xong" },
  { from: "pending_payment", to: "cancelled", label: "Hủy đơn", ownerOnly: true, danger: true },
  { from: "paid", to: "needs_refund", label: "Hủy & hoàn tiền", ownerOnly: true, danger: true },
  { from: "needs_refund", to: "cancelled", label: "Đã hoàn tiền", ownerOnly: true },
];
