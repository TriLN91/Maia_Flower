import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { Template } from "../api/types";
import { BouquetArt, flowerDot } from "../components/BouquetArt";
import { ArrowRightIcon, ClockIcon, LeafIcon, ShieldIcon, SparkleIcon, TruckIcon, UserIcon } from "../components/icons";
import { CardSkeleton, Empty, ErrorBox, Section, TemplateCard } from "../components/ui";
import { earliestLabel, useEarliestSlot } from "../lib/delivery";
import { friendlyError } from "../lib/errors";
import { money } from "../lib/format";

const SORTS = [
  { value: "name", label: "Tên A–Z" },
  { value: "price_asc", label: "Giá thấp → cao" },
  { value: "price_desc", label: "Giá cao → thấp" },
];

const PRICE_RANGES = [
  { id: "all", label: "Mọi mức giá", test: () => true },
  { id: "lt300", label: "Dưới 300k", test: (p: number) => p < 300_000 },
  { id: "300-500", label: "300k – 500k", test: (p: number) => p >= 300_000 && p <= 500_000 },
  { id: "gt500", label: "Trên 500k", test: (p: number) => p > 500_000 },
];

const mainColor = (t: Template) => t.items[0]?.flower_type.color ?? "";
const mainFlower = (t: Template) => t.items[0]?.flower_type;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`flex min-h-10 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium transition ${active ? "bg-ink text-white" : "bg-white text-stone-700 ring-1 ring-stone-200 hover:ring-stone-300"}`}
    >
      {children}
    </button>
  );
}

function Hero({ featured }: { featured?: Template }) {
  const earliest = useEarliestSlot();
  return (
    <section className="relative grid items-center gap-8 overflow-hidden rounded-[2rem] bg-paper px-5 py-8 sm:px-10 sm:py-10 lg:grid-cols-[1.1fr_1fr] lg:py-14">
      <div className="relative z-10 animate-fade-up space-y-5">
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-sage-700">
          Tiệm hoa bó thủ công · TP.HCM
        </p>
        <h1 className="font-display text-[2.15rem] font-semibold leading-[1.12] text-ink sm:text-5xl lg:text-6xl">
          Hoa tươi mỗi sáng,
          <br />
          <em className="font-medium text-brand-700">bó bằng tay</em> cho người bạn thương
        </h1>
        <p className="max-w-md text-base leading-relaxed text-stone-600">
          Chọn một mẫu, thợ Maia cắm ngay từ những cành tươi nhất trong kho và giao đúng khung giờ
          bạn hẹn.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:flex">
          <a
            href="#cua-hang"
            className="inline-flex min-h-12 items-center justify-center gap-2 whitespace-nowrap rounded-full bg-brand-700 px-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-800 sm:px-6 sm:text-base"
          >
            Chọn mẫu hoa <ArrowRightIcon className="size-4" />
          </a>
          <a
            href="#uu-dai"
            className="inline-flex min-h-12 items-center justify-center whitespace-nowrap rounded-full bg-white px-3 text-sm font-semibold text-brand-800 ring-1 ring-brand-200 hover:bg-brand-50 sm:px-6 sm:text-base"
          >
            Ưu đãi hôm nay
          </a>
        </div>
        <p className="flex items-center gap-2 text-sm text-stone-600" aria-live="polite">
          <ClockIcon className="text-sage-700" />
          {earliest.data ? (
            <span>
              Đặt bây giờ, giao sớm nhất <b className="text-ink">{earliestLabel(earliest.data)}</b>
            </span>
          ) : (
            <span>Giao theo khung giờ, 7 ngày trong tuần</span>
          )}
        </p>
      </div>

      <div className="relative mx-auto w-full max-w-[14rem] sm:max-w-sm">
        <div className="absolute -inset-6 rounded-full bg-brand-100/60 blur-2xl" aria-hidden />
        {featured ? (
          <Link
            to={`/mau/${featured.slug}`}
            className="relative block overflow-hidden rounded-[1.75rem] shadow-2xl shadow-brand-900/10 ring-1 ring-white"
          >
            <BouquetArt template={featured} />
            <span className="absolute inset-x-4 bottom-4 flex items-center justify-between rounded-2xl bg-white/90 px-4 py-3 backdrop-blur">
              <span>
                <span className="block font-display text-lg font-semibold text-ink">{featured.name}</span>
                <span className="text-sm text-stone-500">
                  {money(featured.final_price ?? featured.price)}
                </span>
              </span>
              <span className="flex size-10 items-center justify-center rounded-full bg-brand-700 text-white">
                <ArrowRightIcon className="size-4" />
              </span>
            </span>
          </Link>
        ) : (
          <div className="relative aspect-[4/5] animate-pulse rounded-[1.75rem] bg-white/60" />
        )}
      </div>
    </section>
  );
}

const PROMISES = [
  { icon: LeafIcon, title: "Hoa nhập mỗi sáng", text: "Hồng Đà Lạt, tulip Hà Lan… tuyển chọn từng cành" },
  { icon: TruckIcon, title: "Giao trong 2 giờ", text: "Chọn khung giờ, phí tính theo quãng đường thật" },
  { icon: ShieldIcon, title: "Giữ hoa 15 phút", text: "Hoa và khung giờ được giữ khi bạn thanh toán" },
  { icon: UserIcon, title: "Không cần tài khoản", text: "Đặt nhanh, theo dõi đơn bằng đường link riêng" },
];

function Promises() {
  return (
    <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {PROMISES.map(({ icon: Icon, title, text }) => (
        <li key={title} className="flex flex-col gap-2 rounded-2xl bg-white p-4 ring-1 ring-stone-200/70 sm:flex-row sm:gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sage-50 text-sage-700">
            <Icon />
          </span>
          <span>
            <span className="block text-sm font-semibold text-ink">{title}</span>
            <span className="block text-xs leading-relaxed text-stone-500">{text}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

const STEPS = [
  { n: "01", title: "Chọn mẫu bó", text: "Xem thành phần từng bó, thêm nhiều mẫu vào một đơn." },
  { n: "02", title: "Ghim nơi nhận & giờ giao", text: "Phí ship tính ngay theo quãng đường, chọn khung giờ còn chỗ." },
  { n: "03", title: "Thợ bó & giao tận tay", text: "Theo dõi đơn từng bước: đã thanh toán, đang bó, đang giao." },
];

export function HomePage() {
  const [sort, setSort] = useState("name");
  const [color, setColor] = useState<string>("all");
  const [range, setRange] = useState("all");
  const fresh = useQuery({ queryKey: ["fresh-today"], queryFn: api.freshToday });
  const all = useQuery({ queryKey: ["templates", sort], queryFn: () => api.templates(sort) });

  const items = all.data?.items ?? [];
  const loaded = !!all.data && !!fresh.data;
  useEffect(() => {
    // Vào bằng link "/#uu-dai", "/#cua-hang": cuộn tới mục đó khi dữ liệu đã hiện
    if (loaded && window.location.hash) {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
    }
  }, [loaded]);
  const colors = useMemo(() => {
    const m = new Map<string, Template>();
    for (const t of items) if (!m.has(mainColor(t))) m.set(mainColor(t), t);
    return [...m.entries()];
  }, [items]);
  const test = PRICE_RANGES.find((r) => r.id === range)!.test;
  const shown = items.filter(
    (t) => (color === "all" || mainColor(t) === color) && test(t.final_price ?? t.price),
  );
  const featured = fresh.data?.[0] ?? items[0];

  return (
    <div className="space-y-14 sm:space-y-20">
      <div className="space-y-4">
        <Hero featured={featured} />
        <Promises />
      </div>

      {fresh.data && fresh.data.length > 0 && (
        <Section
          id="uu-dai"
          eyebrow="Ưu đãi hoa tươi"
          title="Đẹp nhất là hôm nay"
          subtitle={
            <>
              Giá tự giảm khi một loại hoa trong kho cần bán sớm: hoa vẫn tươi, bạn được giá tốt, shop
              không phải bỏ hoa. Ưu đãi cập nhật mỗi giờ.
            </>
          }
          action={
            <span className="flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-800">
              <SparkleIcon className="size-4" /> {fresh.data.length} mẫu đang giảm giá
            </span>
          }
        >
          <div className="no-scrollbar -mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 lg:mx-0 lg:grid lg:grid-cols-4 lg:overflow-visible lg:px-0">
            {fresh.data.map((t) => (
              <div key={t.id} className="w-[46%] shrink-0 snap-start sm:w-[31%] lg:w-auto">
                <TemplateCard template={t} />
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section
        id="cua-hang"
        eyebrow="Bộ sưu tập"
        title="Tất cả mẫu hoa"
        subtitle="Mỗi mẫu là một công thức cố định: bạn biết chính xác mình nhận được những cành hoa nào."
        action={
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="min-h-10 rounded-full border-0 bg-white px-4 text-sm ring-1 ring-stone-200"
            aria-label="Sắp xếp"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        }
      >
        <div className="space-y-3">
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4" role="group" aria-label="Lọc theo tông màu">
            <Chip active={color === "all"} onClick={() => setColor("all")}>
              Tất cả tông màu
            </Chip>
            {colors.map(([c, t]) => {
              const f = mainFlower(t)!;
              return (
                <Chip key={c} active={color === c} onClick={() => setColor(c)}>
                  <span className="size-3.5 rounded-full ring-1 ring-black/10" style={{ background: flowerDot(f.name, f.color) }} />
                  {cap(c)}
                </Chip>
              );
            })}
          </div>
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4" role="group" aria-label="Lọc theo giá">
            {PRICE_RANGES.map((r) => (
              <Chip key={r.id} active={range === r.id} onClick={() => setRange(r.id)}>
                {r.label}
              </Chip>
            ))}
          </div>
        </div>

        {all.error && <ErrorBox message={friendlyError(all.error)} onRetry={() => all.refetch()} />}
        {all.data && items.length === 0 && (
          <Empty icon={<LeafIcon className="size-9" />} title="Shop chưa có mẫu nào">
            Quay lại sau nhé!
          </Empty>
        )}
        {all.data && items.length > 0 && shown.length === 0 && (
          <div className="rounded-3xl bg-white p-8 text-center text-stone-500 ring-1 ring-stone-200/70">
            Không có mẫu nào khớp bộ lọc.{" "}
            <button
              className="font-semibold text-brand-700 underline"
              onClick={() => {
                setColor("all");
                setRange("all");
              }}
            >
              Bỏ lọc
            </button>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 lg:grid-cols-4">
          {all.isPending && Array.from({ length: 8 }, (_, i) => <CardSkeleton key={i} />)}
          {shown.map((t) => (
            <TemplateCard key={t.id} template={t} />
          ))}
        </div>
      </Section>

      <Section id="cach-dat" eyebrow="Đơn giản trong 3 bước" title="Cách đặt hoa ở Maia">
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-3xl bg-white p-6 ring-1 ring-stone-200/70">
              <span className="font-display text-4xl font-semibold text-brand-200">{s.n}</span>
              <h3 className="mt-2 font-display text-xl font-semibold text-ink">{s.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-stone-500">{s.text}</p>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
