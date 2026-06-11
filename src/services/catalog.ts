import AsyncStorage from '@react-native-async-storage/async-storage';
import { ModelInfo } from '../types';

// Remote "Featured" catalog, served from the GitHub repo via the jsDelivr CDN.
// Edit catalog/featured.json and push — no app rebuild needed to update it.
const CATALOG_URL =
  'https://cdn.jsdelivr.net/gh/poddarhi/EkamCore@app-main/catalog/featured.json';
const CACHE_KEY = 'ekamcore.featuredCatalog.v1';

const isNonEmptyString = (v: unknown): v is string =>
  typeof v === 'string' && v.length > 0;

/**
 * Validate a parsed remote catalog. Accepts `{ models: [...] }`, keeps only
 * entries with the required fields, and returns null if the shape is unusable.
 */
export function validateCatalog(data: unknown): ModelInfo[] | null {
  if (!data || typeof data !== 'object') {
    return null;
  }
  const models = (data as { models?: unknown }).models;
  if (!Array.isArray(models)) {
    return null;
  }
  const valid = models.filter((m: any): m is ModelInfo => {
    return (
      m &&
      typeof m === 'object' &&
      isNonEmptyString(m.id) &&
      isNonEmptyString(m.name) &&
      isNonEmptyString(m.url) &&
      isNonEmptyString(m.params) &&
      isNonEmptyString(m.quant) &&
      typeof m.sizeBytes === 'number' &&
      m.sizeBytes > 0
    );
  });
  return valid.length > 0 ? valid : null;
}

/** Read the last-cached Featured catalog, or null. */
export async function loadCachedCatalog(): Promise<ModelInfo[] | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as ModelInfo[];
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Fetch the remote Featured catalog, validate it, cache it, and return it.
 * Returns null on any network/parse/validation failure (caller falls back).
 */
export async function fetchFeaturedCatalog(): Promise<ModelInfo[] | null> {
  try {
    const res = await fetch(CATALOG_URL, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      return null;
    }
    const models = validateCatalog(await res.json());
    if (models) {
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(models));
    }
    return models;
  } catch {
    return null;
  }
}
