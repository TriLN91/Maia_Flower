import type { ReactNode } from "react";

export function Card({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="font-bold text-stone-800">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200">
      <p className="text-sm text-stone-500">{label}</p>
      <p className="mt-1 text-2xl font-extrabold tabular-nums text-stone-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-stone-500">{hint}</p>}
    </div>
  );
}

/** Thanh độ tươi: 1 = vừa nhập, 0 = hết hạn. Kèm chữ % để không phụ thuộc màu. */
export function FreshnessBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-stone-400">—</span>;
  const pct = Math.round(value * 100);
  const tone = pct > 60 ? "bg-emerald-500" : pct > 30 ? "bg-amber-500" : "bg-red-500";
  return (
    <span className="flex items-center gap-2" title={`Độ tươi ${pct}%`}>
      <span className="h-2 w-20 overflow-hidden rounded-full bg-stone-100">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs tabular-nums text-stone-600">{pct}%</span>
    </span>
  );
}

export const inputCls =
  "min-h-11 w-full rounded-xl border-0 bg-white px-3 ring-1 ring-stone-200 focus:ring-2 focus:ring-brand-400";

export function PageTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h1 className="text-xl font-extrabold">{children}</h1>
      {action}
    </div>
  );
}
