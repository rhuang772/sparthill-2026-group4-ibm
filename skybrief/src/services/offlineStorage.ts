import type { BriefingPack, FlightPlan, PilotProfile } from '../types';

const DB_NAME = 'skybrief-local-v1';
const STORE = 'records';
const PROFILE_KEY = 'skybrief:pilotProfile';
const PLAN_KEY = 'skybrief:flightPlan';
export interface SavedBriefing {
  id: string;
  savedAt: string;
  flightPlan: FlightPlan | null;
  briefing: BriefingPack;
  demo: boolean;
  sources?: { weather?: { data: unknown; fetchedAt: string }; faa?: { data: unknown; fetchedAt: string } };
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function operation<T>(mode: IDBTransactionMode, cb: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const req = cb(tx.objectStore(STORE));
    let result: T;
    req.onsuccess = () => { result = req.result; };
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onerror = () => { db.close(); reject(tx.error); };
    tx.onabort = () => { db.close(); reject(tx.error); };
  });
}
export async function saveLocal<T>(key: string, value: T): Promise<void> {
  await operation('readwrite', store => store.put(value, key));
}
export async function readLocal<T>(key: string): Promise<T | undefined> {
  return operation<T | undefined>('readonly', store => store.get(key));
}
export async function deleteLocal(key: string): Promise<void> {
  await operation('readwrite', store => store.delete(key));
}
export async function saveBriefing(data: Omit<SavedBriefing, 'id' | 'savedAt'>): Promise<SavedBriefing> {
  const record: SavedBriefing = { ...data, id: crypto.randomUUID(), savedAt: new Date().toISOString() };
  await saveLocal(`briefing:${record.id}`, record);
  return record;
}
export async function listBriefings(): Promise<SavedBriefing[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const results: SavedBriefing[] = [];
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor) {
        if (typeof cursor.key === 'string' && cursor.key.startsWith('briefing:')) results.push(cursor.value as SavedBriefing);
        cursor.continue();
      }
    };
    tx.oncomplete = () => { db.close(); resolve(results.sort((a, b) => b.savedAt.localeCompare(a.savedAt))); };
    tx.onerror = () => { db.close(); reject(tx.error); };
  });
}
export function deleteBriefing(id: string) { return deleteLocal(`briefing:${id}`); }
export async function clearPrivateData(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  localStorage.removeItem(PROFILE_KEY);
  localStorage.removeItem(PLAN_KEY);
}
// Small user preferences belong in browser localStorage, not in the backend.
export function readPreferences<T>(kind: 'profile' | 'flightPlan'): T | null {
  const key = kind === 'profile' ? PROFILE_KEY : PLAN_KEY;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : null;
  } catch { return null; }
}
export function savePreferences<T>(kind: 'profile' | 'flightPlan', value: T): void {
  localStorage.setItem(kind === 'profile' ? PROFILE_KEY : PLAN_KEY, JSON.stringify(value));
}
export type SavedProfile = PilotProfile;
export type SavedPlan = FlightPlan;
