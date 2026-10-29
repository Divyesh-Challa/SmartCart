import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, postJson, type Product, type Store } from "../lib/api";
import { useAuth } from "../lib/auth";
import { loadLocation } from "../lib/storage";
import { localDate } from "../lib/format";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, TextInput } from "../components/ui";
import ReceiptReader from "../components/ReceiptReader";

const today = () => localDate();

export default function AddPricePage() {
  const { enabled, session } = useAuth();
  const location = loadLocation();
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [storeId, setStoreId] = useState("");
  const [productQuery, setProductQuery] = useState("");
  const [productId, setProductId] = useState<number | null>(null);
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(today);
  const [isSale, setIsSale] = useState(false);
  const [source, setSource] = useState<"receipt" | "manual">("receipt");
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ radius_km: "15" });
    if (location) params.set("postal_code", location.postalCode);
    api<{ stores: Store[] }>(`/api/stores/nearby?${params}`).then((r) => setStores(r.stores)).catch(() => setStores([]));
  }, [location?.postalCode]);

  useEffect(() => {
    const q = productQuery.trim();
    if (q.length < 2) return setProducts([]);
    const handle = setTimeout(() => {
      api<{ products: Product[] }>(`/api/products?q=${encodeURIComponent(q)}`).then((r) => setProducts(r.products)).catch(() => setProducts([]));
    }, 250);
    return () => clearTimeout(handle);
  }, [productQuery]);

  if (!enabled) return <><PageTitle>{t.addPrice.title}</PageTitle><Notice>{t.account.unavailable}</Notice></>;
  if (!session) {
    return (
      <>
        <PageTitle>{t.addPrice.title}</PageTitle>
        <Notice>{t.addPrice.signIn} <Link to="/account" className="font-semibold underline">{t.account.signInTitle}</Link></Notice>
      </>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setMessage(null);
    try {
      const res = await postJson<{ status: string }>("/api/prices/observations", {
        store_id: Number(storeId),
        price: Number(price),
        product_id: productId,
        item_name: productId ? undefined : productQuery.trim(),
        observed_on: date,
        is_sale: isSale,
        source,
      });
      setMessage({ tone: "success", text: res.status === "accepted" ? t.addPrice.thanks : t.addPrice.pending });
      setPrice("");
      setProductQuery("");
      setProductId(null);
    } catch (err) {
      setMessage({ tone: "error", text: (err as Error).message || t.errors.generic });
    }
  }

  return (
    <>
      <PageTitle>{t.addPrice.title}</PageTitle>
      <p className="text-slate-600 dark:text-slate-400">{t.addPrice.intro}</p>
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <label htmlFor="store" className="block">
            <span className="mb-1 block text-sm font-medium">{t.addPrice.store}</span>
            <select id="store" required value={storeId} onChange={(e) => setStoreId(e.target.value)}
              className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-700 dark:bg-slate-900">
              <option value="">{t.addPrice.chooseStore}</option>
              {stores.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.address ? `, ${s.address}` : ""}{s.distance_km != null ? ` (${s.distance_km} km)` : ""}
                </option>
              ))}
            </select>
          </label>

          <div>
            <TextInput id="item" label={t.addPrice.item} placeholder={t.addPrice.itemPlaceholder} required value={productQuery}
              onChange={(e) => { setProductQuery(e.target.value); setProductId(null); }} autoComplete="off" />
            {products.length > 0 && productId === null && (
              <ul className="mt-1 rounded-xl border border-slate-200 dark:border-slate-700" role="listbox" aria-label={t.addPrice.item}>
                {products.map((p) => (
                  <li key={p.id}>
                    <button type="button" role="option" aria-selected={false} className="w-full px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                      onClick={() => { setProductId(p.id); setProductQuery(p.name); }}>
                      {p.name} <span className="text-xs text-slate-500">({p.package_quantity} {p.package_unit})</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <TextInput id="price" label={t.addPrice.price} type="number" inputMode="decimal" step="0.01" min="0.05" required
              value={price} onChange={(e) => setPrice(e.target.value)} />
            <TextInput id="date" label={t.addPrice.date} type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
          </div>

          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t.addPrice.source}</legend>
            <label className="mr-4"><input type="radio" name="source" checked={source === "receipt"} onChange={() => setSource("receipt")} /> {t.addPrice.receipt}</label>
            <label><input type="radio" name="source" checked={source === "manual"} onChange={() => setSource("manual")} /> {t.addPrice.shelf}</label>
          </fieldset>

          <label className="flex items-center gap-2">
            <input type="checkbox" checked={isSale} onChange={(e) => setIsSale(e.target.checked)} /> {t.addPrice.sale}
          </label>

          <Button type="submit" className="w-full">{t.addPrice.submit}</Button>
        </form>
        {message && <div className="mt-3"><Notice tone={message.tone}>{message.text}</Notice></div>}
      </Card>
      <ReceiptReader storeId={storeId} date={date} />
    </>
  );
}
