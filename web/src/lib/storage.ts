// Per-device state kept in localStorage. Reads tolerate missing or blocked storage.

export interface ListItem {
  id: string;
  name: string;
  quantity: number;
}

export interface SavedLocation {
  postalCode: string;
  area: string;
}

const KEYS = { list: "sc.list.v1", location: "sc.location.v1" };

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: keep working in memory */
  }
}

export const loadList = () => read<ListItem[]>(KEYS.list, []);
export const saveList = (items: ListItem[]) => write(KEYS.list, items);
export const loadLocation = () => read<SavedLocation | null>(KEYS.location, null);
export const saveLocation = (loc: SavedLocation) => write(KEYS.location, loc);
