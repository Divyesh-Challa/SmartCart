import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useShoppingList } from "../lib/shoppingList";
import { t } from "../i18n/en";
import { Button, Card, PageTitle } from "../components/ui";

export default function ListPage() {
  const { items, setItems, status } = useShoppingList();
  const [name, setName] = useState("");

  function add(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setItems((prev) => [...prev, { id: crypto.randomUUID(), name: trimmed, quantity: 1 }]);
    setName("");
  }

  const setQty = (id: string, quantity: number) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, quantity: Math.max(1, quantity) } : it)));

  return (
    <>
      <PageTitle>{t.list.title}</PageTitle>
      <p className="-mt-2 text-xs text-slate-500" aria-live="polite">{t.list.sync[status]}</p>
      <form onSubmit={add} className="flex gap-2">
        <label htmlFor="new-item" className="sr-only">{t.list.itemPlaceholder}</label>
        <input id="new-item" value={name} onChange={(e) => setName(e.target.value)} placeholder={t.list.itemPlaceholder}
          className="min-h-11 flex-1 rounded-xl border border-slate-300 px-3 dark:border-slate-700 dark:bg-slate-900" />
        <Button type="submit">{t.list.add}</Button>
      </form>

      {items.length === 0 ? (
        <p className="text-slate-600 dark:text-slate-400">{t.list.empty}</p>
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {items.map((it) => (
              <li key={it.id} className="flex items-center gap-3 p-3">
                <span className="flex-1">{it.name}</span>
                <label className="sr-only" htmlFor={`qty-${it.id}`}>{`${t.list.qty} ${it.name}`}</label>
                <input id={`qty-${it.id}`} type="number" min={1} value={it.quantity}
                  onChange={(e) => setQty(it.id, Number(e.target.value) || 1)}
                  className="min-h-11 w-16 rounded-lg border border-slate-300 px-2 text-center dark:border-slate-700 dark:bg-slate-900" />
                <button type="button" aria-label={t.list.remove(it.name)} className="min-h-11 min-w-11 rounded-lg text-xl text-slate-500"
                  onClick={() => setItems((prev) => prev.filter((p) => p.id !== it.id))}>×</button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {items.length > 0 && (
        <div className="flex gap-2">
          <Link to="/plan" className="flex min-h-11 flex-1 items-center justify-center rounded-xl bg-brand-700 px-4 font-semibold text-white">
            {t.list.plan}
          </Link>
          <Button variant="secondary" onClick={() => setItems([])}>{t.list.clear}</Button>
        </div>
      )}
    </>
  );
}
