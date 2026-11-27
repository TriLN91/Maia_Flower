/**
 * Gốc URL của API.
 * - Dev: để trống -> gọi `/api/v1` cùng origin, Vite proxy sang backend.
 * - Production (Static Site riêng): đặt lúc build, vd. VITE_API_BASE_URL=https://maia-flower.onrender.com
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export const apiUrl = (path: string) => `${API_BASE}/api/v1${path}`;
