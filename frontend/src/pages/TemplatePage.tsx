import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import { BouquetArt, flowerDot } from "../components/BouquetArt";
import { CheckIcon, ChevronDownIcon, ChevronLeftIcon, ClockIcon, GiftIcon, LeafIcon, SparkleIcon, TruckIcon } from "../components/icons";
import { BottomBar, Button, DiscountBadge, ErrorBox, Loading, Price, Stepper, TemplateCard } from "../components/ui";
import { cart } from "../lib/cart";
import { earliestLabel, useEarliestSlot } from "../lib/delivery";
import { friendlyError } from "../lib/errors";
import { money } from "../lib/format";

function Details({ title, icon, children, open }: { title: string; icon: ReactNode; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="group border-b border-stone-200 py-1 [&_summary::-webkit-details-marker]:hidden">
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 font-semibold text-ink">
        <span className="text-sage-700">{icon}</span>
        <span className="flex-1">{title}</span>
        <ChevronDownIcon className="text-stone-400 transition group-open:rotate-180" />
      </summary>
      <div className="pb-4 pl-8 text-sm leading-relaxed text-stone-600">{children}</div>
    </details>
  );
}

export function TemplatePage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);
  const q = useQuery({ queryKey: ["template", slug], queryFn: () => api.template(slug) });
  const others = useQuery({ queryKey: ["templates", "name"], queryFn: () => api.templates("name") });
  const earliest = useEarliestSlot();
  useEffect(() => {
    // Bấm sang mẫu khác (mục "Có thể bạn cũng thích") -> làm mới lựa chọn
    setQty(1);
    setAdded(false);
  }, [slug]);

  if (q.isPending) return <Loading />;
  if (q.error)
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <ErrorBox message={friendlyError(q.error)} />
        <Link to="/" className="font-semibold text-brand-700">
          ← Về trang chủ
        </Link>
      </div>
    );

  const t = q.data;
  const unit = t.final_price ?? t.price;
  const stems = t.items.reduce((n, i) => n + i.quantity, 0);
  const saving = t.price - unit;
  const related = (others.data?.items ?? []).filter((x) => x.id !== t.id).slice(0, 4);

  const add = () => {
    cart.add(t.id, qty);
    setAdded(true);
  };
  const cta = added ? (
    <Button className="flex-1" onClick={() => navigate("/gio-hang")}>
      <CheckIcon className="size-4" /> Xem giỏ hàng
    </Button>
  ) : (
    <Button className="flex-1" onClick={add}>
      <span className="whitespace-nowrap">
        Thêm<span className="hidden sm:inline"> vào giỏ</span> · {money(unit * qty)}
      </span>
    </Button>
  );

  return (
    <div className="space-y-16">
      <article className="grid gap-6 lg:grid-cols-2 lg:gap-12">
        <div className="lg:sticky lg:top-24 lg:self-start">
          <Link to="/" className="mb-3 inline-flex min-h-10 items-center gap-1 text-sm font-medium text-stone-500 hover:text-brand-700">
            <ChevronLeftIcon className="size-4" /> Tất cả mẫu hoa
          </Link>
          <div className="relative -mx-4 overflow-hidden sm:mx-0 sm:rounded-[2rem] sm:ring-1 sm:ring-stone-200/70">
            <BouquetArt template={t} className="aspect-square sm:aspect-[4/5] lg:aspect-[4/5]" />
            {t.discount_pct > 0 && (
              <DiscountBadge pct={t.discount_pct} className="absolute left-4 top-4 px-3 text-sm" />
            )}
          </div>
        </div>

        <div className="space-y-6 lg:pt-12">
          <div className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[.18em] text-sage-700">
              Bó hoa · {stems} cành
            </p>
            <h1 className="font-display text-4xl font-semibold leading-tight text-ink sm:text-5xl">{t.name}</h1>
            <div className="flex flex-wrap items-center gap-3">
              <Price price={t.price} finalPrice={t.final_price} pct={t.discount_pct} size="lg" />
              {saving > 0 && (
                <span className="rounded-full bg-sage-50 px-3 py-1 text-xs font-semibold text-sage-800">
                  Tiết kiệm {money(saving)}
                </span>
              )}
            </div>
            {t.description && <p className="text-base leading-relaxed text-stone-600">{t.description}</p>}
          </div>

          {t.discount_pct > 0 && (
            <div className="flex gap-3 rounded-2xl bg-brand-50 p-4 text-sm text-brand-900">
              <SparkleIcon className="mt-0.5 text-brand-600" />
              <p>
                <b>Ưu đãi hoa tươi hôm nay.</b> Kho đang có nhiều hoa cho mẫu này nên giá tự giảm. Hoa vẫn
                tươi như thường, đây là lúc mua được giá tốt nhất.
              </p>
            </div>
          )}

          <div className="rounded-2xl bg-white p-4 ring-1 ring-stone-200/70">
            <p className="flex items-center gap-2 text-sm text-stone-600">
              <ClockIcon className="text-sage-700" />
              {earliest.data ? (
                <span>
                  Giao sớm nhất <b className="text-ink">{earliestLabel(earliest.data)}</b>
                </span>
              ) : (
                <span>Chọn ngày và khung giờ giao ở bước đặt hàng</span>
              )}
            </p>
            <div className="mt-4 hidden items-center gap-3 lg:flex">
              <Stepper value={qty} onChange={setQty} label="Số lượng bó" />
              {cta}
            </div>
          </div>

          <div>
            <Details title={`Thành phần (${stems} cành)`} icon={<LeafIcon />} open>
              <ul className="divide-y divide-stone-100">
                {t.items.map((i) => (
                  <li key={i.flower_type.id} className="flex items-center gap-3 py-2.5">
                    <span
                      className="size-3.5 rounded-full ring-1 ring-black/10"
                      style={{ background: flowerDot(i.flower_type.name, i.flower_type.color) }}
                    />
                    <span className="flex-1 text-ink">{i.flower_type.name}</span>
                    <span className="font-medium tabular-nums text-stone-500">× {i.quantity}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-stone-500">
                Thợ chọn những cành tươi nhất trong kho cho bó của bạn. Sắc độ có thể khác nhẹ so với
                hình minh hoạ.
              </p>
            </Details>
            <Details title="Giao hàng" icon={<TruckIcon />}>
              Giao theo khung giờ bạn chọn trong 7 ngày tới. Phí ship tính theo quãng đường thực tế từ
              shop tới nơi nhận, hiện rõ trước khi thanh toán. Shop giữ hoa và khung giờ cho bạn 15 phút
              trong lúc thanh toán.
            </Details>
            <Details title="Tặng người thương" icon={<GiftIcon />}>
              Ở bước đặt hàng, chọn "Tặng người khác" để nhập tên, số điện thoại người nhận và lời nhắn.
              Shop viết tay lời nhắn lên thiệp đi kèm bó hoa.
            </Details>
            <Details title="Chăm sóc hoa" icon={<SparkleIcon />}>
              Cắt xéo cuống 1–2 cm, cắm vào bình nước sạch ngập 1/3 cuống, thay nước mỗi ngày và để nơi
              thoáng mát, tránh nắng trực tiếp.
            </Details>
          </div>
        </div>
      </article>

      {related.length > 0 && (
        <section className="space-y-5">
          <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">Có thể bạn cũng thích</h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-4">
            {related.map((r) => (
              <TemplateCard key={r.id} template={r} />
            ))}
          </div>
        </section>
      )}

      <BottomBar desktopHidden>
        <Stepper value={qty} onChange={setQty} label="Số lượng bó" />
        {cta}
      </BottomBar>
    </div>
  );
}
