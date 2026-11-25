// Kiểu dữ liệu khớp với schema của backend (FastAPI /docs).

export interface FlowerBrief {
  id: number;
  name: string;
  color: string;
}

export interface Template {
  id: number;
  name: string;
  slug: string;
  description: string;
  image_url: string | null;
  price: number;
  discount_pct: number;
  final_price: number | null;
  items: { flower_type: FlowerBrief; quantity: number }[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ShopInfo {
  shop_address: string;
  shop_lat: number;
  shop_lng: number;
  max_delivery_km: number;
  base_fee: number;
  base_km: number;
  free_ship_min_subtotal: number | null;
  free_ship_max_km: number;
  hold_minutes: number;
  booking_window_days: number;
  address_search_enabled: boolean;
}

export interface CartLine {
  template_id: number;
  quantity: number;
}

export interface CartQuote {
  lines: {
    template_id: number;
    name: string;
    quantity: number;
    unit_price: number;
    discount_pct: number;
    line_total: number;
    available: boolean;
  }[];
  subtotal: number;
  discount_total: number;
  delivery_fee: number | null;
  total: number;
  all_available: boolean;
}

export interface DeliveryQuote {
  distance_km: number;
  provider: "goong" | "haversine";
  base_fee: number;
  distance_fee: number;
  holiday_surcharge: number;
  free_shipping: boolean;
  fee: number;
  quote_token: string;
  expires_at: string;
}

export interface Slot {
  slot_id: number;
  date: string;
  start_time: string;
  end_time: string;
  capacity: number;
  remaining: number;
  bookable: boolean;
  reason: "FULL" | "CLOSED" | "TOO_LATE" | "OUT_OF_WINDOW" | null;
}

export interface PlaceSuggestion {
  place_id: string;
  description: string;
  main_text: string;
  secondary_text: string;
}

export type OrderStatus =
  | "pending_payment"
  | "paid"
  | "preparing"
  | "delivering"
  | "completed"
  | "cancelled"
  | "expired"
  | "needs_refund";

export interface Order {
  code: string;
  status: OrderStatus;
  customer_name: string;
  customer_phone_masked: string;
  recipient_name: string | null;
  delivery_address: string;
  delivery_starts_at: string;
  delivery_ends_at: string;
  card_message: string | null;
  items: {
    template_id: number;
    template_name: string;
    quantity: number;
    unit_price: number;
    discount_pct: number;
    line_total: number;
  }[];
  subtotal: number;
  discount_total: number;
  delivery_fee: number;
  total: number;
  hold_expires_at: string | null;
  created_at: string;
  timeline: { to_status: OrderStatus; created_at: string }[];
  tracking_token?: string;
}

export interface PaymentStart {
  payment_url: string;
  txn_ref: string;
  amount: number;
  expires_at: string;
}

export interface PaymentReturn {
  order_code: string;
  payment_status: "pending" | "succeeded" | "failed" | "cancelled";
  order_status: OrderStatus;
  gateway_success: boolean;
  message: string;
}
