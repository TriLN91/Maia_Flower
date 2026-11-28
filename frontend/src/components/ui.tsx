import { useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router";
import type { Template } from "../api/types";
import { cart } from "../lib/cart";
import { money } from "../lib/format";
import { BouquetArt, flowerDot } from "./BouquetArt";
import { CheckIcon, PlusIcon } from "./icons";

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
    primary:
      "bg-brand-700 text-white shadow-sm shadow-brand-900/10 hover:bg-brand-800 active:scale-[.98] disabled:bg-brand-300 disabled:shadow-none",
    secondary:
      "bg-white text-brand-800 ring-1 ring-brand-200 hover:bg-brand-50 disabled:opacity-50",
    ghost: "text-brand-700 hover:bg-brand-50 disabled:opacity-50",
  }[variant];
  return (
    <button
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-5 font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 ${styles} ${className}`}
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
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${small ? "size-4" : "size-8 text-brand-500"}`}
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
    <div role="alert" className="rounded-2xl bg-red-50 p-4 text-sm text-red-800 ring-1 ring-red-200">
      <p>{message}</p>
      {onRetry && (
        <button className="mt-2 font-semibold underline" onClick={onRetry}>
          Thử lại
        </button>
      )}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      <span className="flex size-20 items-center justify-center rounded-full bg-brand-50 text-4xl text-brand-600">
        {icon}
      </span>
      <h2 className="font-display text-2xl font-semibold text-ink">{title}</h2>
      <div className="text-stone-500">{children}</div>
    </div>
  );
}

export function Price({
  price,
  finalPrice,
  pct,
  size = "md",
}: {
  price: number;
  finalPrice?: number | null;
  pct?: number;
  size?: "md" | "lg";
}) {
  const big = size === "lg" ? "text-2xl" : "text-base";
  if (pct && finalPrice != null && finalPrice < price) {
    return (
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className={`font-bold tabular-nums text-brand-700 ${big}`}>{money(finalPrice)}</span>
        <span className="text-sm tabular-nums text-stone-400 line-through">{money(price)}</span>
      </span>
    );
  }
  return <span className={`font-bold tabular-nums text-ink ${big}`}>{money(price)}</span>;
}

export function DiscountBadge({ pct, className = "" }: { pct: number; className?: string }) {
  return (
    <span
      className={`rounded-full bg-brand-700 px-2.5 py-1 text-xs font-bold tracking-wide text-white shadow-sm ${className}`}
    >
      −{pct}%
    </span>
  );
}

/** Chấm màu + tên hoa chính — tóm tắt thành phần cho thẻ sản phẩm. */
export function Composition({ template, className = "" }: { template: Template; className?: string }) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <span className="flex -space-x-1">
        {template.items.slice(0, 4).map((i) => (
          <span
            key={i.flower_type.id}
            className="size-3 rounded-full ring-2 ring-white"
            style={{ background: flowerDot(i.flower_type.name, i.flower_type.color) }}
          />
        ))}
      </span>
      <span className="line-clamp-1 text-xs text-stone-500">
        {template.items
          .filter((i) => !i.flower_type.name.toLowerCase().startsWith("lá"))
          .map((i) => i.flower_type.name)
          .join(" · ")}
      </span>
    </div>
  );
}

const STRETCHED_LINK = "after:absolute after:inset-0 after:content-['']";

export function TemplateCard({ template }: { template: Template }) {
  const [added, setAdded] = useState(false);
  return (
    <div className="group relative flex flex-col overflow-hidden rounded-3xl bg-white ring-1 ring-stone-200/70 transition hover:-translate-y-0.5 hover:shadow-xl hover:shadow-brand-900/5">
      <div className="relative overflow-hidden">
        <div className="transition duration-500 group-hover:scale-[1.04]">
          <BouquetArt template={template} />
        </div>
        {template.discount_pct > 0 && (
          <DiscountBadge pct={template.discount_pct} className="absolute left-3 top-3" />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3 sm:p-4">
        <h3 className="font-display text-[1.05rem] font-semibold leading-snug text-ink sm:text-lg">
          {/* Cả thẻ bấm được (link phủ toàn thẻ), riêng nút "+" là thêm nhanh vào giỏ */}
          <Link to={`/mau/${template.slug}`} className={STRETCHED_LINK}>
            {template.name}
          </Link>
        </h3>
        <Composition template={template} />
        <div className="mt-auto flex items-end justify-between gap-2 pt-1">
          <Price price={template.price} finalPrice={template.final_price} pct={template.discount_pct} />
          <button
            type="button"
            onClick={() => {
              cart.add(template.id, 1);
              setAdded(true);
              window.setTimeout(() => setAdded(false), 1600);
            }}
            className={`relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full transition ${added ? "bg-sage-500 text-white" : "bg-brand-50 text-brand-700 hover:bg-brand-700 hover:text-white"}`}
            aria-label={added ? `Đã thêm ${template.name} vào giỏ` : `Thêm 1 bó ${template.name} vào giỏ`}
          >
            {added ? <CheckIcon /> : <PlusIcon />}
          </button>
        </div>
      </div>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="overflow-hidden rounded-3xl bg-white ring-1 ring-stone-200/70" aria-hidden>
      <div className="aspect-[4/5] animate-pulse bg-paper" />
      <div className="space-y-2 p-4">
        <div className="h-4 w-3/4 animate-pulse rounded bg-stone-100" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-stone-100" />
        <div className="h-4 w-1/3 animate-pulse rounded bg-stone-100" />
      </div>
    </div>
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
    <div className="inline-flex items-center rounded-full bg-white ring-1 ring-stone-200" role="group" aria-label={label}>
      <button
        type="button"
        className="size-11 rounded-full text-xl text-stone-600 hover:bg-stone-50 disabled:opacity-30"
        onClick={() => onChange(value - 1)}
        disabled={value <= min}
        aria-label="Giảm"
      >
        −
      </button>
      <span className="w-7 text-center font-semibold tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className="size-11 rounded-full text-xl text-stone-600 hover:bg-stone-50 disabled:opacity-30"
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
export function BottomBar({ children, desktopHidden }: { children: ReactNode; desktopHidden?: boolean }) {
  return (
    <>
      {/* Chừa chỗ để thanh cố định không che nội dung cuối trang */}
      <div className={`h-20 ${desktopHidden ? "lg:hidden" : ""}`} aria-hidden />
      <div
      className={`pb-safe fixed inset-x-0 bottom-0 z-[1000] border-t border-stone-200/80 bg-cream/95 px-4 pt-3 backdrop-blur ${desktopHidden ? "lg:hidden" : ""}`}
    >
      <div className="mx-auto flex max-w-2xl items-center gap-3">{children}</div>
      </div>
    </>
  );
}

export function Section({
  title,
  eyebrow,
  subtitle,
  children,
  action,
  id,
}: {
  title: string;
  eyebrow?: string;
  subtitle?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <section className="scroll-mt-24 space-y-5" id={id}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          {eyebrow && (
            <p className="text-xs font-semibold uppercase tracking-[.18em] text-sage-700">{eyebrow}</p>
          )}
          <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">{title}</h2>
          {subtitle && <p className="max-w-xl text-sm text-stone-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-3xl bg-white p-5 ring-1 ring-stone-200/70 ${className}`}>{children}</section>;
}
