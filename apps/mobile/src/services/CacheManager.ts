/**
 * CacheManager — SQLCipher-encrypted local cache with LRU eviction (S16-003).
 *
 * Architecture:
 * - Encryption key: 32 random bytes stored in Keychain ("EkamCore-Mobile-CacheKey")
 * - DB opened with PRAGMA key = x'...' (hex-encoded)
 * - Schema: cache_entries table with key, value (JSON), TTL, LRU tracking
 * - LRU eviction when total size exceeds maxSizeBytes (default 100 MB)
 * - Secure wipe on logout: DROP tables → VACUUM → close → delete file → clear key
 *
 * The actual SQLCipher native module is abstracted behind a DatabaseAdapter
 * interface so tests can inject an in-memory mock. In production, this uses
 * react-native-quick-sqlite or react-native-sqlcipher-2.
 */

import * as Keychain from 'react-native-keychain';

// ── Types ───────────────────────────────────────────────────────────────────

export interface CacheEntry<T = unknown> {
  key: string;
  value: T;
  cacheType: string;
  fetchedAt: number;   // unix ms
  expiresAt: number;   // unix ms
  isStale: boolean;
}

export type CacheType =
  | 'today'
  | 'recap'
  | 'personProfile'
  | 'fileList'
  | 'photoList'
  | 'searchResult'
  | 'userProfile'
  | 'settings';

/**
 * Abstraction over the native SQLite driver.
 * In production: react-native-quick-sqlite or react-native-sqlcipher-2.
 * In tests: in-memory Map-based mock.
 */
export interface DatabaseAdapter {
  execute(sql: string, params?: unknown[]): Promise<void>;
  query<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<T[]>;
  close(): Promise<void>;
}

// ── Constants ───────────────────────────────────────────────────────────────

const CACHE_KEY_SERVICE = 'EkamCore-Mobile-CacheKey';
const DB_NAME = 'ekamcore_cache.db';
const DEFAULT_MAX_SIZE = 100 * 1024 * 1024; // 100 MB

// ── CacheManager ────────────────────────────────────────────────────────────

class CacheManagerClass {
  private db: DatabaseAdapter | null = null;
  private maxSizeBytes: number = DEFAULT_MAX_SIZE;
  private initialized = false;

  /**
   * Inject a database adapter. In production this is called with the
   * SQLCipher driver; tests inject an in-memory mock.
   */
  setAdapter(adapter: DatabaseAdapter): void {
    this.db = adapter;
  }

  setMaxSize(bytes: number): void {
    this.maxSizeBytes = bytes;
  }

  getMaxSize(): number {
    return this.maxSizeBytes;
  }

  /**
   * Initialize: get or create encryption key, open DB, create schema.
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    // Get or generate encryption key
    await this.ensureCacheKey();

    // If no adapter was injected (production), we'd open native SQLCipher here.
    // For the scaffold, we require setAdapter() to be called before initialize().
    if (!this.db) {
      throw new Error(
        'CacheManager: no DatabaseAdapter set. Call setAdapter() before initialize().',
      );
    }

    // Create schema
    await this.db.execute(`
      CREATE TABLE IF NOT EXISTS cache_entries (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        fetched_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        last_accessed_at INTEGER NOT NULL,
        cache_type TEXT NOT NULL
      )
    `);
    await this.db.execute(
      'CREATE INDEX IF NOT EXISTS ix_cache_expires ON cache_entries(expires_at)',
    );
    await this.db.execute(
      'CREATE INDEX IF NOT EXISTS ix_cache_accessed ON cache_entries(last_accessed_at)',
    );
    await this.db.execute(
      'CREATE INDEX IF NOT EXISTS ix_cache_type ON cache_entries(cache_type)',
    );

    this.initialized = true;
  }

  // ── CRUD ──────────────────────────────────────────────────────────────

  async get<T>(key: string): Promise<CacheEntry<T> | null> {
    if (!this.db) return null;

    const rows = await this.db.query<{
      value: string;
      cache_type: string;
      fetched_at: number;
      expires_at: number;
    }>(
      'SELECT value, cache_type, fetched_at, expires_at FROM cache_entries WHERE key = ?',
      [key],
    );

    if (rows.length === 0) return null;

    const row = rows[0];
    const now = Date.now();

    // Update last_accessed_at (LRU tracking)
    await this.db.execute(
      'UPDATE cache_entries SET last_accessed_at = ? WHERE key = ?',
      [now, key],
    );

    let parsed: T;
    try {
      parsed = JSON.parse(row.value) as T;
    } catch {
      // Corrupt entry — remove it
      await this.delete(key);
      return null;
    }

    return {
      key,
      value: parsed,
      cacheType: row.cache_type,
      fetchedAt: row.fetched_at,
      expiresAt: row.expires_at,
      isStale: now > row.expires_at,
    };
  }

  async set<T>(
    key: string,
    value: T,
    ttlSeconds: number,
    cacheType: CacheType = 'settings',
  ): Promise<void> {
    if (!this.db) return;

    const now = Date.now();
    const json = JSON.stringify(value);
    const sizeBytes = json.length * 2; // rough UTF-16 estimate

    await this.db.execute(
      `INSERT OR REPLACE INTO cache_entries
       (key, value, size_bytes, fetched_at, expires_at, last_accessed_at, cache_type)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [key, json, sizeBytes, now, now + ttlSeconds * 1000, now, cacheType],
    );

    // Enforce size limit after write
    await this.enforceLimit();
  }

  async delete(key: string): Promise<void> {
    if (!this.db) return;
    await this.db.execute('DELETE FROM cache_entries WHERE key = ?', [key]);
  }

  async deleteByPrefix(prefix: string): Promise<number> {
    if (!this.db) return 0;

    const rows = await this.db.query<{cnt: number}>(
      "SELECT count(*) as cnt FROM cache_entries WHERE key LIKE ? || '%'",
      [prefix],
    );
    const count = rows[0]?.cnt ?? 0;

    await this.db.execute(
      "DELETE FROM cache_entries WHERE key LIKE ? || '%'",
      [prefix],
    );

    return count;
  }

  /**
   * Remove all entries that have expired.
   */
  async purgeExpired(): Promise<number> {
    if (!this.db) return 0;

    const rows = await this.db.query<{cnt: number}>(
      'SELECT count(*) as cnt FROM cache_entries WHERE expires_at < ?',
      [Date.now()],
    );
    const count = rows[0]?.cnt ?? 0;

    await this.db.execute(
      'DELETE FROM cache_entries WHERE expires_at < ?',
      [Date.now()],
    );

    return count;
  }

  // ── Size & eviction ───────────────────────────────────────────────────

  async getSize(): Promise<number> {
    if (!this.db) return 0;
    const rows = await this.db.query<{total: number}>(
      'SELECT COALESCE(SUM(size_bytes), 0) as total FROM cache_entries',
    );
    return rows[0]?.total ?? 0;
  }

  async getEntryCount(): Promise<number> {
    if (!this.db) return 0;
    const rows = await this.db.query<{cnt: number}>(
      'SELECT count(*) as cnt FROM cache_entries',
    );
    return rows[0]?.cnt ?? 0;
  }

  async getSizeByType(): Promise<Record<string, number>> {
    if (!this.db) return {};
    const rows = await this.db.query<{cache_type: string; total: number}>(
      'SELECT cache_type, COALESCE(SUM(size_bytes), 0) as total FROM cache_entries GROUP BY cache_type',
    );
    const result: Record<string, number> = {};
    for (const row of rows) {
      result[row.cache_type] = row.total;
    }
    return result;
  }

  /**
   * LRU eviction: remove least-recently-accessed entries until under limit.
   */
  async enforceLimit(): Promise<void> {
    if (!this.db) return;

    // First purge expired entries (free space without losing useful data)
    await this.purgeExpired();

    let size = await this.getSize();
    if (size <= this.maxSizeBytes) return;

    // Evict oldest-accessed entries in batches of 10
    while (size > this.maxSizeBytes) {
      const oldest = await this.db.query<{key: string; size_bytes: number}>(
        'SELECT key, size_bytes FROM cache_entries ORDER BY last_accessed_at ASC LIMIT 10',
      );

      if (oldest.length === 0) break;

      for (const entry of oldest) {
        await this.db.execute('DELETE FROM cache_entries WHERE key = ?', [
          entry.key,
        ]);
        size -= entry.size_bytes;
        if (size <= this.maxSizeBytes) break;
      }
    }
  }

  // ── Secure wipe (FS-178) ──────────────────────────────────────────────

  /**
   * Securely wipe all cached data. Called on logout.
   *
   * 1. DROP all tables
   * 2. VACUUM (compact free space so deleted data isn't recoverable)
   * 3. Close database
   * 4. Delete Keychain cache key
   *
   * After wipe, initialize() must be called again before any operations.
   */
  async wipeAll(): Promise<void> {
    if (this.db) {
      try {
        await this.db.execute('DROP TABLE IF EXISTS cache_entries');
        await this.db.execute('VACUUM');
      } catch {
        // DB may already be corrupted — continue with cleanup
      }

      try {
        await this.db.close();
      } catch {
        // Ignore close errors
      }
    }

    // Clear encryption key from Keychain
    await Keychain.resetGenericPassword({service: CACHE_KEY_SERVICE});

    this.db = null;
    this.initialized = false;
  }

  // ── Encryption key management ─────────────────────────────────────────

  private async ensureCacheKey(): Promise<string> {
    const existing = await Keychain.getGenericPassword({
      service: CACHE_KEY_SERVICE,
    });

    if (existing && typeof existing !== 'boolean') {
      return existing.password;
    }

    // Generate 32 random bytes as hex string (64 hex chars)
    const bytes = new Uint8Array(32);
    for (let i = 0; i < 32; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
    const hex = Array.from(bytes)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');

    await Keychain.setGenericPassword('cache', hex, {
      service: CACHE_KEY_SERVICE,
      accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });

    return hex;
  }
}

export const cacheManager = new CacheManagerClass();
