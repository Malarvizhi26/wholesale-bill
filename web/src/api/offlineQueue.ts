// Offline counter invoice queue.
//
// When POST /billing/invoices fails because the server could not be reached (not an HTTP error),
// the full invoice body is kept in localStorage with a device-series invoice number and pushed
// later through POST /billing/sync-invoices. The server accepts every queued bill (conflicts such
// as negative stock or credit limit are returned as review_flags) and re-sent numbers are
// idempotent, so a bill is only removed from this queue once the server reports it SYNCED.
import type { SyncInvoiceResult } from '../types';
import { api, isNetworkError } from './client';

const QUEUE_KEY = 'hbos.offlineInvoiceQueue.v1';
const DEVICE_KEY = 'hbos.deviceCode.v1';
const SEQ_KEY = 'hbos.offlineInvoiceSeq.v1';

export interface QueuedInvoice {
  invoice_number: string;
  queued_at: string;
  status: 'PENDING' | 'ERROR';
  error?: string;
  attempts: number;
  grand_total: number;
  customer_name: string;
  body: Record<string, any>;
}

export interface SyncOutcome {
  synced: Array<{ invoice_number: string; review_flags: string[] }>;
  failed: Array<{ invoice_number: string; error: string }>;
  networkError: boolean;
}

type Listener = (queue: QueuedInvoice[]) => void;
const listeners = new Set<Listener>();

const safeGet = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const safeSet = (key: string, value: string): void => {
  // Not caught on purpose for the queue itself: a bill that cannot be stored must not be reported as saved
  localStorage.setItem(key, value);
};

export const getQueue = (): QueuedInvoice[] => {
  const raw = safeGet(QUEUE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveQueue = (queue: QueuedInvoice[]) => {
  safeSet(QUEUE_KEY, JSON.stringify(queue));
  listeners.forEach(l => l(queue));
};

export const subscribeQueue = (listener: Listener): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

// Another browser tab of the same counter changed the queue
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === QUEUE_KEY) listeners.forEach(l => l(getQueue()));
  });
}

// Stable per-browser device code so two offline counters never issue the same number
const deviceCode = (): string => {
  let code = safeGet(DEVICE_KEY);
  if (!code) {
    code = Math.random().toString(36).slice(2, 6).toUpperCase().padEnd(4, 'X');
    try {
      localStorage.setItem(DEVICE_KEY, code);
    } catch {
      // fall through with an unsaved code
    }
  }
  return code;
};

// Indian financial year label (April-March), e.g. 26-27
const fyLabel = (d: Date): string => {
  const y = d.getFullYear() % 100;
  const start = d.getMonth() >= 3 ? y : (y + 99) % 100;
  return `${String(start).padStart(2, '0')}-${String((start + 1) % 100).padStart(2, '0')}`;
};

// Device offline series, e.g. C1-OF-7KQ2/26-27/0001 (distinct from the server's C1/26-27/ series so an
// offline number can never collide with - and be mistaken for - an invoice the server already posted)
export const nextOfflineInvoiceNumber = (now = new Date()): string => {
  const fy = fyLabel(now);
  const seqKey = `${SEQ_KEY}.${fy}`;
  const next = (parseInt(safeGet(seqKey) || '0', 10) || 0) + 1;
  safeSet(seqKey, String(next));
  return `C1-OF-${deviceCode()}/${fy}/${String(next).padStart(4, '0')}`;
};

// Queue an invoice body that could not reach the server. Returns the offline invoice number.
export const enqueueOfflineInvoice = (
  body: Record<string, any>,
  meta: { grand_total: number; customer_name: string },
): string => {
  const now = new Date();
  const invoice_number = nextOfflineInvoiceNumber(now);
  const item: QueuedInvoice = {
    invoice_number,
    queued_at: now.toISOString(),
    status: 'PENDING',
    attempts: 0,
    grand_total: meta.grand_total,
    customer_name: meta.customer_name,
    body: {
      ...body,
      invoice_number,
      invoice_date: now.toISOString(),
      is_offline_created: true,
      offline_created_at: now.toISOString(),
    },
  };
  saveQueue([...getQueue(), item]);
  return invoice_number;
};

export const pendingCount = (): number => getQueue().length;

let inFlight: Promise<SyncOutcome> | null = null;

// Push queued bills. includeErrored=true also retries bills the server previously rejected.
export const syncOfflineInvoices = (includeErrored = false): Promise<SyncOutcome> => {
  if (inFlight) return inFlight;
  inFlight = (async (): Promise<SyncOutcome> => {
    const outcome: SyncOutcome = { synced: [], failed: [], networkError: false };
    const toSend = getQueue().filter(q => q.status === 'PENDING' || includeErrored);
    if (toSend.length === 0) return outcome;

    let results: SyncInvoiceResult[];
    try {
      results = await api.syncInvoices(toSend.map(q => q.body));
    } catch (e: any) {
      outcome.networkError = isNetworkError(e);
      if (!outcome.networkError) {
        // Whole batch refused (e.g. 422 validation): keep every bill, mark them for attention
        const msg = e?.message || 'Sync failed';
        saveQueue(getQueue().map(q => toSend.some(s => s.invoice_number === q.invoice_number)
          ? { ...q, status: 'ERROR', error: msg, attempts: q.attempts + 1 }
          : q));
        toSend.forEach(q => outcome.failed.push({ invoice_number: q.invoice_number, error: msg }));
      }
      return outcome;
    }

    const byNumber = new Map(results.map(r => [r.invoice_number ?? '', r]));
    const remaining: QueuedInvoice[] = [];
    // Re-read: bills queued while the request was in flight must be kept
    for (const q of getQueue()) {
      const r = byNumber.get(q.invoice_number);
      if (!toSend.some(s => s.invoice_number === q.invoice_number) || !r) {
        remaining.push(q);
      } else if (r.status === 'SYNCED') {
        outcome.synced.push({ invoice_number: q.invoice_number, review_flags: r.review_flags || [] });
      } else {
        const error = r.error || 'Rejected by server';
        outcome.failed.push({ invoice_number: q.invoice_number, error });
        remaining.push({ ...q, status: 'ERROR', error, attempts: q.attempts + 1 });
      }
    }
    saveQueue(remaining);
    return outcome;
  })().finally(() => {
    inFlight = null;
  });
  return inFlight;
};
