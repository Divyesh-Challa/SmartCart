import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { loadList, saveList, type ListItem } from "./storage";

export type SyncStatus = "local" | "syncing" | "synced" | "error";

/** The account's list, plus anything added on this device that it doesn't have yet (matched by name). */
export function mergeLists(server: ListItem[], local: ListItem[]): ListItem[] {
  const names = new Set(server.map((it) => it.name.trim().toLowerCase()));
  return [...server, ...local.filter((it) => !names.has(it.name.trim().toLowerCase()))];
}

const sameItems = (a: ListItem[], b: ListItem[]) => JSON.stringify(a) === JSON.stringify(b);

/**
 * The shopping list, kept on the device and, when signed in, synced to the
 * account so it follows the shopper across devices. Last write wins.
 */
export function useShoppingList() {
  const { session } = useAuth();
  const [items, setItems] = useState<ListItem[]>(loadList);
  const [status, setStatus] = useState<SyncStatus>("local");
  // The user whose account list has been loaded; saving waits for that.
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const lastSaved = useRef<ListItem[] | null>(null);
  const userId = session?.user.id ?? null;

  useEffect(() => saveList(items), [items]);

  // On sign-in, fetch the account's list and merge in this device's items.
  useEffect(() => {
    setLoadedFor(null);
    if (!userId) {
      setStatus("local");
      return;
    }
    let cancelled = false;
    setStatus("syncing");
    api<{ items: ListItem[] }>("/api/me/list")
      .then((remote) => {
        if (cancelled) return;
        lastSaved.current = remote.items;
        setItems((local) => mergeLists(remote.items, local));
        setLoadedFor(userId);
        setStatus("synced");
      })
      .catch(() => !cancelled && setStatus("error"));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  // Once loaded, save changes to the account shortly after they stop.
  useEffect(() => {
    if (!userId || loadedFor !== userId) return;
    if (lastSaved.current && sameItems(lastSaved.current, items)) return;
    setStatus("syncing");
    const timer = setTimeout(() => {
      api("/api/me/list", { method: "PUT", body: JSON.stringify({ items }) })
        .then(() => {
          lastSaved.current = items;
          setStatus("synced");
        })
        .catch(() => setStatus("error"));
    }, 800);
    return () => clearTimeout(timer);
  }, [items, userId, loadedFor]);

  return { items, setItems, status };
}
