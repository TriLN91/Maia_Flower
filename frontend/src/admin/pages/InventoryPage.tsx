import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button, ErrorBox, Loading } from "../../components/ui";
import { friendlyError } from "../../lib/errors";
import { dateTime, money } from "../../lib/format";
import { admin, useSession, type Batch } from "../api";
import { Card, FreshnessBar, PageTitle, inputCls } from "../ui";

const BATCH_STATUS: Record<Batch["status"], string> = {
  active: "Đang bán",
  needs_review: "Cần xem xét",
  depleted: "Hết hàng",
  discarded: "Đã bỏ",
};

function ImportForm({ onDone }: { onDone: () => void }) {
  const flowers = useQuery({ queryKey: ["flower-types"], queryFn: admin.flowerTypes });
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: admin.suppliers });
  const [form, setForm] = useState({ flower_type_id: 0, supplier_id: 0, quantity: 50, cost_per_stem: 8000 });
  const save = useMutation({ mutationFn: () => admin.importBatch(form), onSuccess: onDone });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="grid gap-3 md:grid-cols-5">
      <select required value={form.flower_type_id || ""} onChange={(e) => setForm({ ...form, flower_type_id: +e.target.value })} className={inputCls} aria-label="Loại hoa">
        <option value="">Loại hoa…</option>
        {flowers.data?.filter((f) => f.is_active).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
      </select>
      <select required value={form.supplier_id || ""} onChange={(e) => setForm({ ...form, supplier_id: +e.target.value })} className={inputCls} aria-label="Nhà cung cấp">
        <option value="">Nhà cung cấp…</option>
        {suppliers.data?.filter((s) => s.is_active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <label className="flex items-center gap-2"><span className="text-sm text-stone-500">Số cành</span>
        <input type="number" min={1} required value={form.quantity} onChange={(e) => setForm({ ...form, quantity: +e.target.value })} className={inputCls} /></label>
      <label className="flex items-center gap-2"><span className="text-sm text-stone-500">Giá/cành</span>
        <input type="number" min={0} step={100} required value={form.cost_per_stem} onChange={(e) => setForm({ ...form, cost_per_stem: +e.target.value })} className={inputCls} /></label>
      <Button type="submit" loading={save.isPending}>Nhập lô</Button>
      {save.error && <div className="md:col-span-5"><ErrorBox message={friendlyError(save.error)} /></div>}
    </form>
  );
}

function BatchRow({ b, owner }: { b: Batch; owner: boolean }) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["batches"] });
    qc.invalidateQueries({ queryKey: ["inventory"] });
  };
  const waste = useMutation({
    mutationFn: (n: number) => admin.waste(b.id, n, "Hoa hỏng (ghi từ trang quản trị)"),
    onSuccess: refresh,
  });
  const discard = useMutation({ mutationFn: () => admin.discard(b.id, "Bỏ lô từ trang quản trị"), onSuccess: refresh });
  const open = b.status === "active" || b.status === "needs_review";
  return (
    <tr className="border-t border-stone-100 align-middle">
      <td className="py-2 pr-2 font-mono text-xs">#{b.id}</td>
      <td className="pr-2">{b.supplier.name}</td>
      <td className="pr-2 tabular-nums">{b.quantity_available}/{b.quantity_received}</td>
      <td className="pr-2"><FreshnessBar value={b.freshness} /></td>
      <td className="pr-2 text-xs text-stone-600">{dateTime(b.expected_expiry_at)}{b.days_left < 0 ? " (quá hạn)" : ""}</td>
      <td className="pr-2 text-xs">{BATCH_STATUS[b.status]}</td>
      <td className="whitespace-nowrap text-right">
        {open && b.quantity_available > 0 && (
          <>
            <button className="min-h-9 rounded-lg px-2 text-xs font-semibold text-amber-700 hover:bg-amber-50"
              onClick={() => {
                const n = Number(window.prompt(`Số cành hỏng ở lô #${b.id} (còn ${b.quantity_available})?`, "1"));
                if (n > 0) waste.mutate(n);
              }}>Ghi hỏng</button>
            {owner && (
              <button className="min-h-9 rounded-lg px-2 text-xs font-semibold text-red-700 hover:bg-red-50"
                onClick={() => window.confirm(`Bỏ toàn bộ ${b.quantity_available} cành còn lại của lô #${b.id}?`) && discard.mutate()}>Bỏ lô</button>
            )}
          </>
        )}
        {(waste.error || discard.error) && <span className="block text-xs text-red-600">{friendlyError(waste.error ?? discard.error)}</span>}
      </td>
    </tr>
  );
}

/** Lô còn hoa (đang bán / cần xem xét) theo thứ tự FEFO; không còn lô nào thì hiện 5 lô gần nhất. */
const shownBatches = (all: Batch[]) => {
  const open = all.filter((b) => b.status === "active" || b.status === "needs_review");
  return open.length ? open : all.slice(-5);
};

export function InventoryPage() {
  const owner = useSession()?.role === "owner";
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [showImport, setShowImport] = useState(false);
  const inventory = useQuery({ queryKey: ["inventory"], queryFn: admin.inventory });
  const batches = useQuery({
    queryKey: ["batches", selected],
    queryFn: () => admin.batches({ flower_type_id: selected! }),
    enabled: selected != null,
  });

  if (inventory.isPending) return <Loading />;
  if (inventory.error) return <ErrorBox message={friendlyError(inventory.error)} />;
  const sel = inventory.data.find((s) => s.flower_type.id === selected);

  return (
    <div className="space-y-4">
      <PageTitle action={<Button onClick={() => setShowImport((v) => !v)}>{showImport ? "Đóng" : "+ Nhập lô"}</Button>}>Kho hoa</PageTitle>
      {showImport && (
        <Card title="Nhập lô mới">
          <ImportForm onDone={() => {
            setShowImport(false);
            qc.invalidateQueries({ queryKey: ["inventory"] });
            qc.invalidateQueries({ queryKey: ["batches"] });
          }} />
        </Card>
      )}
      <Card title="Tồn theo loại hoa">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-stone-500">
              <tr><th className="pb-2">Loại hoa</th><th>Bán được</th><th>Sắp hết hạn</th><th>Độ tươi TB</th><th>Lô</th></tr>
            </thead>
            <tbody>
              {inventory.data.map((s) => (
                <tr key={s.flower_type.id} onClick={() => setSelected(s.flower_type.id)}
                  className={`cursor-pointer border-t border-stone-100 hover:bg-brand-50/50 ${selected === s.flower_type.id ? "bg-brand-50" : ""}`}>
                  <td className="py-2 font-medium">{s.flower_type.name}</td>
                  <td className="tabular-nums">{s.sellable}</td>
                  <td className={`tabular-nums ${s.expiring_soon ? "font-semibold text-amber-700" : "text-stone-400"}`}>{s.expiring_soon || "—"}</td>
                  <td><FreshnessBar value={s.avg_freshness} /></td>
                  <td className="tabular-nums text-stone-500">{s.batch_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-stone-500">Chạm một dòng để xem các lô (sắp theo hạn dùng — thứ tự FEFO).</p>
      </Card>
      {selected != null && (
        <Card title={`Lô ${sel?.flower_type.name ?? ""}`}>
          {batches.isPending && <Loading />}
          {batches.data && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="text-left text-xs text-stone-500">
                  <tr><th className="pb-2">Lô</th><th>NCC</th><th>Còn/nhập</th><th>Độ tươi</th><th>Hạn dùng</th><th>Trạng thái</th><th /></tr>
                </thead>
                <tbody>
                  {shownBatches(batches.data).map((b) => <BatchRow key={b.id} b={b} owner={owner} />)}
                </tbody>
              </table>
            </div>
          )}
          {batches.data && <p className="mt-2 text-xs text-stone-500">Giá nhập gần nhất: {money(batches.data.at(-1)?.cost_per_stem ?? 0)}/cành</p>}
        </Card>
      )}
    </div>
  );
}
