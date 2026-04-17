import {cacheManager, type DatabaseAdapter} from '../services/CacheManager';
import {__clearStore} from '../__mocks__/react-native-keychain';

// ── In-memory DatabaseAdapter mock ──────────────────────────────────────────

class InMemoryDB implements DatabaseAdapter {
  private tables: Map<string, Map<string, Record<string, unknown>>> = new Map();
  private closed = false;

  async execute(sql: string, params: unknown[] = []): Promise<void> {
    if (this.closed) throw new Error('DB closed');

    const normalized = sql.trim().toUpperCase();

    if (normalized.startsWith('CREATE TABLE') || normalized.startsWith('CREATE INDEX')) {
      // Schema operations — no-op for in-memory
      if (normalized.includes('CACHE_ENTRIES') && !this.tables.has('cache_entries')) {
        this.tables.set('cache_entries', new Map());
      }
      return;
    }

    if (normalized.startsWith('DROP TABLE')) {
      this.tables.delete('cache_entries');
      return;
    }

    if (normalized.startsWith('VACUUM')) return;

    const entries = this.tables.get('cache_entries');
    if (!entries) return;

    if (normalized.startsWith('INSERT OR REPLACE')) {
      const [key, value, size_bytes, fetched_at, expires_at, last_accessed_at, cache_type] =
        params as [string, string, number, number, number, number, string];
      entries.set(key, {key, value, size_bytes, fetched_at, expires_at, last_accessed_at, cache_type});
      return;
    }

    if (normalized.startsWith('UPDATE')) {
      const lastAccessed = params[0] as number;
      const key = params[1] as string;
      const entry = entries.get(key);
      if (entry) entry.last_accessed_at = lastAccessed;
      return;
    }

    if (normalized.startsWith('DELETE')) {
      if (normalized.includes('LIKE')) {
        const prefix = params[0] as string;
        for (const [k] of entries) {
          if (k.startsWith(prefix)) entries.delete(k);
        }
      } else if (normalized.includes('EXPIRES_AT')) {
        const now = params[0] as number;
        for (const [k, v] of entries) {
          if ((v.expires_at as number) < now) entries.delete(k);
        }
      } else {
        const key = params[0] as string;
        entries.delete(key);
      }
      return;
    }
  }

  async query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
    if (this.closed) throw new Error('DB closed');

    const entries = this.tables.get('cache_entries');
    if (!entries) return [] as T[];

    const normalized = sql.trim().toUpperCase();

    // SELECT ... WHERE key = ?
    if (normalized.includes('WHERE KEY =')) {
      const key = params[0] as string;
      const entry = entries.get(key);
      return entry ? [entry as T] : [];
    }

    // count with LIKE prefix
    if (normalized.includes('LIKE') && normalized.includes('COUNT')) {
      const prefix = params[0] as string;
      let cnt = 0;
      for (const k of entries.keys()) {
        if (k.startsWith(prefix)) cnt++;
      }
      return [{cnt} as T];
    }

    // count with expires_at
    if (normalized.includes('EXPIRES_AT') && normalized.includes('COUNT')) {
      const now = params[0] as number;
      let cnt = 0;
      for (const v of entries.values()) {
        if ((v.expires_at as number) < now) cnt++;
      }
      return [{cnt} as T];
    }

    // SUM(size_bytes)
    if (normalized.includes('SUM(SIZE_BYTES)')) {
      let total = 0;
      for (const v of entries.values()) total += v.size_bytes as number;
      return [{total} as T];
    }

    // count(*)
    if (normalized.includes('COUNT(*)')) {
      if (normalized.includes('GROUP BY')) {
        const groups: Record<string, number> = {};
        for (const v of entries.values()) {
          const t = v.cache_type as string;
          groups[t] = (groups[t] ?? 0) + (v.size_bytes as number);
        }
        return Object.entries(groups).map(([cache_type, total]) => ({cache_type, total} as T));
      }
      return [{cnt: entries.size} as T];
    }

    // ORDER BY last_accessed_at ASC LIMIT 10 (LRU eviction)
    if (normalized.includes('ORDER BY LAST_ACCESSED_AT ASC')) {
      const sorted = [...entries.values()].sort(
        (a, b) => (a.last_accessed_at as number) - (b.last_accessed_at as number),
      );
      return sorted.slice(0, 10).map(e => ({key: e.key, size_bytes: e.size_bytes} as T));
    }

    // GROUP BY cache_type SUM
    if (normalized.includes('GROUP BY')) {
      const groups: Record<string, number> = {};
      for (const v of entries.values()) {
        const t = v.cache_type as string;
        groups[t] = (groups[t] ?? 0) + (v.size_bytes as number);
      }
      return Object.entries(groups).map(([cache_type, total]) => ({cache_type, total} as T));
    }

    return [] as T[];
  }

  async close(): Promise<void> {
    this.closed = true;
  }
}

// ── Tests ───────────────────────────────────────────────────────────────────

beforeEach(async () => {
  __clearStore();
  const db = new InMemoryDB();
  cacheManager.setAdapter(db);
  cacheManager.setMaxSize(100 * 1024 * 1024);
  await cacheManager.initialize();
});

describe('CacheManager', () => {
  it('set and get roundtrip', async () => {
    await cacheManager.set('today:2026-04-17', {cards: [1, 2, 3]}, 3600, 'today');
    const entry = await cacheManager.get<{cards: number[]}>('today:2026-04-17');

    expect(entry).not.toBeNull();
    expect(entry!.value.cards).toEqual([1, 2, 3]);
    expect(entry!.cacheType).toBe('today');
    expect(entry!.isStale).toBe(false);
  });

  it('returns null for missing key', async () => {
    const entry = await cacheManager.get('nonexistent');
    expect(entry).toBeNull();
  });

  it('marks entry as stale after TTL expires', async () => {
    // Set with 0-second TTL (already expired)
    await cacheManager.set('search:weather', {results: []}, 0, 'searchResult');

    // Wait a tick so Date.now() advances past expiresAt
    await new Promise<void>(r => setTimeout(r, 10));

    const entry = await cacheManager.get('search:weather');
    expect(entry).not.toBeNull();
    expect(entry!.isStale).toBe(true);
  });

  it('delete removes entry', async () => {
    await cacheManager.set('k1', 'v1', 3600, 'settings');
    await cacheManager.delete('k1');
    const entry = await cacheManager.get('k1');
    expect(entry).toBeNull();
  });

  it('deleteByPrefix removes matching entries', async () => {
    await cacheManager.set('search:a', 'v1', 3600, 'searchResult');
    await cacheManager.set('search:b', 'v2', 3600, 'searchResult');
    await cacheManager.set('today:x', 'v3', 3600, 'today');

    const deleted = await cacheManager.deleteByPrefix('search:');
    expect(deleted).toBe(2);

    const remaining = await cacheManager.getEntryCount();
    expect(remaining).toBe(1);
  });

  it('getSize returns total bytes', async () => {
    await cacheManager.set('a', {big: 'x'.repeat(100)}, 3600, 'today');
    const size = await cacheManager.getSize();
    expect(size).toBeGreaterThan(0);
  });

  it('LRU eviction removes oldest entries when over limit', async () => {
    // Set a very small limit
    cacheManager.setMaxSize(500);

    // Insert entries that together exceed 500 bytes
    for (let i = 0; i < 10; i++) {
      await cacheManager.set(`item:${i}`, {data: 'x'.repeat(50)}, 3600, 'today');
    }

    // After eviction, total size should be under limit
    const size = await cacheManager.getSize();
    expect(size).toBeLessThanOrEqual(500);
  });

  it('wipeAll clears everything and resets state', async () => {
    await cacheManager.set('k1', 'v1', 3600, 'settings');
    await cacheManager.wipeAll();

    // After wipe, get should return null (no DB)
    const entry = await cacheManager.get('k1');
    expect(entry).toBeNull();
  });

  it('getSizeByType groups correctly', async () => {
    await cacheManager.set('today:a', 'val', 3600, 'today');
    await cacheManager.set('search:b', 'val', 3600, 'searchResult');

    const byType = await cacheManager.getSizeByType();
    expect(byType.today).toBeGreaterThan(0);
    expect(byType.searchResult).toBeGreaterThan(0);
  });
});
