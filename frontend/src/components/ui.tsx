import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import type { Template } from "../api/types";
import { gradientFor, money } from "../lib/format";

const FLOWER_EMOJI: Record<string, string> = {
  đỏ: "🌹",
  hồng: "🌷",
  trắng: "🤍",
  kem: "🌼",
  vàng: "🌻",
  tím: "💜",
  xanh: "💐",
};

export function Button({
  variant = "primary",
  className = "",
  loading,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
}) {
  const styles = {
    primary: "bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-300",
    secondary: "bg-white text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50 disabled:opacity-50",
    ghost: "text-rose-700 hover:bg-rose-50 disabled:opacity-50",
  }[variant];
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 font-semibold transition ${styles} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      role="status"
      aria-label="Đang tải"
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${small ? "size-4" : "size-8 text-rose-500"}`}
    />
  );
}

export function Loading({ text = "Đang tải…" }: { text?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-stone-500">
      <Spinner />
      <p>{text}</p>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800 ring-1 ring-red-200">
      <p>{message}</p>
      {onRetry && (
        <button className="mt-2 font-semibold underline" onClick={onRetry}>
          Thử lại
        </button>
      )}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center">
      <span className="text-5xl">{icon}</span>
      <h2 className="text-lg font-semibold text-stone-800">{title}</h2>
      <div className="text-stone-500">{children}</div>
    </div>
  );
}

export function Price({ price, finalPrice, pct }: { price: number; finalPrice?: number | null; pct?: number }) {
  if (pct && finalPrice != null && finalPrice < price) {
    return (
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-bold text-rose-700">{money(finalPrice)}</span>
        <span className="text-sm text-stone-400 line-through">{money(price)}</span>
      </span>
    );
  }
  return <span className="font-bold text-stone-900">{money(price)}</span>;
}

export function BouquetArt({ template, size = "card" }: { template: Template; size?: "card" | "hero" }) {
  const main = template.items[0]?.flower_type.color;
  const emoji = FLOWER_EMOJI[main] ?? "💐";
  if (template.image_url) {
    return (
      <img
        src={template.image_url}
        alt={template.name}
        className={`w-full object-cover ${size === "hero" ? "aspect-square" : "aspect-[4/5]"}`}
        loading="lazy"
      />
    );
  }
  return (
    <div
      aria-hidden
      className={`flex w-full items-center justify-center bg-gradient-to-br ${gradientFor(main)} ${size === "hero" ? "aspect-square text-8xl" : "aspect-[4/5] text-5xl"}`}
    >
      <span className="drop-shadow">{emoji}</span>
    </div>
  );
}

export function TemplateCard({ template }: { template: Template }) {
  return (
    <Link
      to={`/mau/${template.slug}`}
      className="group overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-stone-100 transition hover:shadow-md"
    >
      <div className="relative">
        <BouquetArt template={template} />
        {template.discount_pct > 0 && (
          <span className="absolute left-2 top-2 rounded-full bg-rose-600 px-2 py-0.5 text-xs font-bold text-white">
            −{template.discount_pct}%
          </span>
        )}
      </div>
      <div className="space-y-1 p-3">
        <h3 className="line-clamp-1 font-semibold text-stone-800 group-hover:text-rose-700">
          {template.name}
        </h3>
        <Price price={template.price} finalPrice={template.final_price} pct={template.discount_pct} />
      </div>
    </Link>
  );
}

export function Stepper({
  value,
  onChange,
  min = 1,
  max = 20,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  label: string;
}) {
  return (
    <div className="inline-flex items-center rounded-xl ring-1 ring-stone-200" aria-label={label}>
      <button
        className="size-11 text-xl text-stone-600 disabled:opacity-30"
        onClick={() => onChange(value - 1)}
        disabled={value <= min}
        aria-label="Giảm"
      >
        −
      </button>
      <span className="w-8 text-center font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        className="size-11 text-xl text-stone-600 disabled:opacity-30"
        onClick={() => onChange(value + 1)}
        disabled={value >= max}
        aria-label="Tăng"
      >
        +
      </button>
    </div>
  );
}

/** Thanh hành động dính đáy màn hình (ngón cái bấm dễ trên điện thoại). */
export function BottomBar({ children }: { children: ReactNode }) {
  return (
    <div className="pb-safe fixed inset-x-0 bottom-0 z-[1000] border-t border-stone-200 bg-white/95 px-4 pt-3 backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-center gap-3">{children}</div>
    </div>
  );
}

export function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-stone-800">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
