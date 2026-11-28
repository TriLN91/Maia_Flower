import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { dateTime, money } from "../../lib/format";
import { admin, useSession, type AdminTemplate } from "../api";
import { Card, FreshnessBar, PageTitle, inputCls } from "../ui";

const LIMIT_LABEL: Record<string, string> = {
  step: "giới hạn bước",
  max_discount: "trần giảm",
  margin_floor: "sàn biên lợi nhuận",
  locked: "mẫu khóa giảm giá",
  disabled: "công tắc tổng tắt",
};
const WARNING_LABEL: Record<string, string> = {
  BELOW_COST: "Giá bán thấp hơn giá vốn",
  LOW_MARGIN_AT_MAX_DISCOUNT: "Nếu giảm tối đa, biên lợi nhuận dưới ngưỡng",
};

function TemplateDetail({ t, owner }: { t: AdminTemplate; owner: boolean }) {
  const qc = useQueryClient();
  const [price, setPrice] = useState(t.price);
  const cost = useQuery({ queryKey: ["tpl-cost", t.id], queryFn: () => admin.templateCost(t.id), enabled: owner });
  const log = useQuery({ queryKey: ["tpl-log", t.id], queryFn: () => admin.discountLog(t.id) });
  const save = useMutation({
    mutationFn: (body: Parameters<typeof admin.updateTemplate>[1]) => admin.updateTemplate(t.id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-templates"] });
      qc.invalidateQueries({ queryKey: ["tpl-cost", t.id] });
    },
  });

  return (
    <div className="space-y-3 rounded-xl bg-stone-50 p-3 text-sm">
      <p className="text-stone-600">{t.items.map((i) => `${i.flower_type.name} ×${i.quantity}`).join(" · ")}</p>
      {owner && (
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2">Giá bán
            <input type="number" step={1000} min={1000} value={price} onChange={(e) => setPrice(+e.target.value)} className={`${inputCls} w-36`} />
          </label>
          <Button loading={save.isPending} disabled={price === t.price} onClick={() => save.mutate({ price })}>Lưu giá</Button>
          <label className="flex min-h-11 items-center gap-2">
            <input type="checkbox" checked={t.discount_locked} onChange={(e) => save.mutate({ discount_locked: e.target.checked })} className="size-5 accent-brand-600" />
            Không áp giảm giá động
          </label>
        </div>
      )}
      {save.error && <ErrorBox message={friendlyError(save.error)} />}
      {cost.data && (
        <p>
          Giá vốn hiện tại <b>{money(cost.data.cost)}</b>
          {cost.data.margin_pct != null && <> · biên lợi nhuận <b>{cost.data.margin_pct}%</b></>}
          {" "}· giá sàn {money(cost.data.price_floor)}
        </p>
      )}
      {cost.data?.warnings.map((w) => <p key={w} className="rounded-lg bg-amber-50 px-3 py-2 text-amber-800">⚠ {WARNING_LABEL[w] ?? w}</p>)}
      <div>
        <p className="mb-1 font-semibold">Vì sao giá thay đổi</p>
        {log.data?.length ? (
          <ul className="space-y-1">
            {log.data.slice(0, 5).map((l, k) => (
              <li key={k} className="text-stone-600">
                {dateTime(l.created_at)}: {l.old_pct}% → <b>{l.new_pct}%</b>
                {l.reason.flowers?.length > 0 && <> · dư {l.reason.flowers.map((f) => `${f.name} (${f.surplus})`).join(", ")}</>}
                {l.reason.limits?.length > 0 && <> · bị chặn bởi {l.reason.limits.map((x) => LIMIT_LABEL[x] ?? x).join(", ")} (mục tiêu {l.reason.target_pct}%)</>}
              </li>
            ))}
          </ul>
        ) : <p className="text-stone-500">Chưa từng được giảm giá động.</p>}
      </div>
    </div>
  );
}

export function PricingPage() {
  const owner = useSession()?.role === "owner";
  const qc = useQueryClient();
  const [open, setOpen] = useState<number | null>(null);
  const templates = useQuery({ queryKey: ["admin-templates"], queryFn: admin.templates });
  const urgency = useQuery({ queryKey: ["urgency"], queryFn: admin.urgency });
  const recompute = useMutation({
    mutationFn: admin.recomputePricing,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-templates"] });
      qc.invalidateQueries({ queryKey: ["urgency"] });
      qc.invalidateQueries({ queryKey: ["tpl-log"] });
    },
  });

  if (templates.isPending) return <Loading />;
  if (templates.error) return <ErrorBox message={friendlyError(templates.error)} />;
  const rows = (urgency.data ?? []).filter((u) => u.expiring_qty > 0);

  return (
    <div className="space-y-4">
      <PageTitle action={owner && <Button variant="secondary" loading={recompute.isPending} onClick={() => recompute.mutate()}>Tính lại giảm giá</Button>}>
        Mẫu & giá
      </PageTitle>
      {recompute.data && <p className="text-sm text-emerald-700">✓ Đã tính lại — {recompute.data.templates_changed} mẫu đổi mức giảm.</p>}

      <Card title="🔥 Cần bán gấp">
        <p className="mb-2 text-xs text-stone-500">
          Hoa hết hạn trong 2 ngày tới so với số dự kiến bán (theo dự báo). Chỉ giảm giá khi thật sự dư.
          {urgency.data?.[0] && <> Cập nhật {dateTime(urgency.data[0].computed_at)}.</>}
        </p>
        {rows.length === 0 ? <p className="text-sm text-stone-500">Không có lô nào sắp hết hạn.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-left text-xs text-stone-500">
                <tr><th className="pb-2">Loại hoa</th><th>Sắp hết hạn</th><th>Dự kiến bán</th><th>Dư thừa</th><th>Độ tươi</th><th>Giảm</th></tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.flower_type_id} className="border-t border-stone-100">
                    <td className="py-2 font-medium">{u.name}</td>
                    <td className="tabular-nums">{u.expiring_qty}</td>
                    <td className="tabular-nums">{u.expected_demand}</td>
                    <td className={`tabular-nums ${u.surplus ? "font-bold text-brand-700" : "text-stone-400"}`}>{u.surplus || "—"}</td>
                    <td><FreshnessBar value={u.avg_freshness} /></td>
                    <td className="tabular-nums">{u.discount_pct ? `${u.discount_pct}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Mẫu bó hoa">
        <ul className="divide-y divide-stone-100">
          {templates.data.map((t) => (
            <li key={t.id} className="py-2">
              <button className="flex min-h-11 w-full items-center justify-between gap-2 text-left" onClick={() => setOpen(open === t.id ? null : t.id)} aria-expanded={open === t.id}>
                <span className="font-medium">
                  {t.name}
                  {!t.is_active && <span className="ml-2 text-xs text-stone-400">(ngừng bán)</span>}
                  {t.discount_locked && <span className="ml-2 text-xs text-stone-400">🔒</span>}
                </span>
                <span className="flex items-center gap-2 tabular-nums">
                  {t.current_discount_pct > 0 && <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-bold text-brand-700">−{t.current_discount_pct}%</span>}
                  {money(t.price)}
                </span>
              </button>
              {open === t.id && <TemplateDetail t={t} owner={owner} />}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
