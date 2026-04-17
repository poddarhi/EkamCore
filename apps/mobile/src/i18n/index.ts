/**
 * i18n — minimal translation helper (S16-007 / ART-22).
 *
 * English-only for v1.0. All strings externalized in en.json for future
 * localization. Falls back to key path if translation not found.
 */

import en from './en.json';

type TranslationDict = Record<string, unknown>;

const translations: TranslationDict = en;

/**
 * Translate a dotted key path (e.g. "auth.signIn") to the localized string.
 * Supports simple {placeholder} interpolation.
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const parts = key.split('.');
  let value: unknown = translations;

  for (const part of parts) {
    if (value && typeof value === 'object' && part in (value as Record<string, unknown>)) {
      value = (value as Record<string, unknown>)[part];
    } else {
      return key; // Fallback to key path
    }
  }

  if (typeof value !== 'string') return key;

  let result = value;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      result = result.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
    }
  }

  return result;
}
