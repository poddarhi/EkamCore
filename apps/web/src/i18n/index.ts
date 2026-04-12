/**
 * Simple i18n utility (G-11 / ART-22).
 *
 * Loads the English string catalog and provides a `t()` function
 * with {placeholder} interpolation.  Falls back to the key itself
 * when a translation is missing (logs a warning in dev).
 *
 * No external dependencies — can be swapped for react-intl later
 * when multi-language support is added.
 */

import en from "./en.json";

const translations: Record<string, string> = en;

/**
 * Look up a translated string by key, with optional placeholder interpolation.
 *
 * @param key   - Dot-separated key, e.g. "nav.today" or "today.updated".
 * @param params - Optional map of placeholder values, e.g. { time: "5m ago" }.
 * @returns The translated string, or the key itself if no translation exists.
 *
 * @example
 * t("nav.today")                       // "Today"
 * t("today.updated", { time: "3m ago" }) // "Updated 3m ago"
 * t("missing.key")                      // "missing.key" (+ dev warning)
 */
export function t(key: string, params?: Record<string, string | number>): string {
  let value = translations[key];

  if (value === undefined) {
    if (import.meta.env.DEV) {
      console.warn(`[i18n] Missing translation: "${key}"`);
    }
    return key;
  }

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      value = value.replaceAll(`{${k}}`, String(v));
    }
  }

  return value;
}
