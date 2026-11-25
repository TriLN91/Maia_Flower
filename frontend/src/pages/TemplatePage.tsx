import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import { BottomBar, BouquetArt, Button, ErrorBox, Loading, Price, Stepper } from "../components/ui";
import { cart } from "../lib/cart";
import { friendlyError } from "../lib/errors";
import { money } from "../lib/format";

export function TemplatePage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);
  const q = useQuery({ queryKey: ["template", slug], queryFn: () => api.template(slug) });

  if (q.isPending) return <Loading />;
  if (q.error)
    return (
      <div className="space-y-4">
        <ErrorBox message={friendlyError(q.error)} />
        <Link to="/" className="font-semibold text-rose-700">
          ← Về trang chủ
        </Link>
      </div>
    );

  const t = q.data;
  const unit = t.final_price ?? t.price;
  const stems = t.items.reduce((n, i) => n + i.quantity, 0);

  return (
    <article className="space-y-5">
      <div className="relative -mx-4 overflow-hidden sm:mx-0 sm:rounded-3xl">
        <BouquetArt template={t} size="hero" />
        {t.discount_pct > 0 && (
          <span className="absolute left-4 top-4 rounded-full bg-rose-600 px-3 py-1 text-sm font-bold text-white">
            Ưu đãi hôm nay −{t.discount_pct}%
          </span>
        )}
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-extrabold text-stone-900">{t.name}</h1>
        <div className="text-xl">
          <Price price={t.price} finalPrice={t.final_price} pct={t.discount_pct} />
        </div>
        {t.description && <p className="text-stone-600">{t.description}</p>}
      </div>

      <section className="rounded-2xl bg-white p-4 ring-1 ring-stone-100">
        <h2 className="mb-2 font-semibold">Thành phần ({stems} cành)</h2>
        <ul className="divide-y divide-stone-100">
          {t.items.map((i) => (
            <li key={i.flower_type.id} className="flex justify-between py-2 text-sm">
              <span>{i.flower_type.name}</span>
              <span className="font-medium tabular-nums text-stone-600">× {i.quantity}</span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-stone-500">
          Thợ chọn hoa tươi nhất trong kho cho bó của bạn. Có thể khác nhẹ về sắc độ so với hình.
        </p>
      </section>

      <BottomBar>
        <Stepper value={qty} onChange={setQty} label="Số lượng bó" />
        {added ? (
          <Button className="flex-1" onClick={() => navigate("/gio-hang")}>
            Xem giỏ hàng →
          </Button>
        ) : (
          <Button
            className="flex-1"
            onClick={() => {
              cart.add(t.id, qty);
              setAdded(true);
            }}
          >
            Thêm vào giỏ · {money(unit * qty)}
          </Button>
        )}
      </BottomBar>
    </article>
  );
}
