import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { Empty, ErrorBox, Loading, Section, TemplateCard } from "../components/ui";
import { friendlyError } from "../lib/errors";

const SORTS = [
  { value: "name", label: "Tên A–Z" },
  { value: "price_asc", label: "Giá thấp → cao" },
  { value: "price_desc", label: "Giá cao → thấp" },
];

export function HomePage() {
  const [sort, setSort] = useState("name");
  const fresh = useQuery({ queryKey: ["fresh-today"], queryFn: api.freshToday });
  const all = useQuery({ queryKey: ["templates", sort], queryFn: () => api.templates(sort) });

  return (
    <div className="space-y-8">
      <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-rose-500 to-pink-600 p-6 text-white shadow-lg">
        <p className="text-sm font-medium opacity-90">Hoa tươi mỗi sáng · Giao trong 2 giờ</p>
        <h1 className="mt-1 text-2xl font-extrabold leading-tight">
          Chọn mẫu bó hoa,
          <br />
          thợ Maia bó ngay cho bạn
        </h1>
        <p className="mt-2 text-sm opacity-90">
          Không cần tạo tài khoản. Giữ hoa 15 phút trong lúc bạn thanh toán.
        </p>
      </section>

      {fresh.data && fresh.data.length > 0 && (
        <Section title="🌿 Tươi nhất hôm nay">
          <p className="-mt-1 text-sm text-stone-500">
            Hoa vừa về và đang được ưu đãi — đẹp nhất là ngay hôm nay.
          </p>
          <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2">
            {fresh.data.map((t) => (
              <div key={t.id} className="w-40 shrink-0 snap-start">
                <TemplateCard template={t} />
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section
        title="Tất cả mẫu"
        action={
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="min-h-11 rounded-xl border-0 bg-white px-3 text-sm ring-1 ring-stone-200"
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
        {all.isPending && <Loading />}
        {all.error && <ErrorBox message={friendlyError(all.error)} onRetry={() => all.refetch()} />}
        {all.data && all.data.items.length === 0 && (
          <Empty icon="🥀" title="Shop chưa có mẫu nào">
            Quay lại sau nhé!
          </Empty>
        )}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {all.data?.items.map((t) => <TemplateCard key={t.id} template={t} />)}
        </div>
      </Section>
    </div>
  );
}
