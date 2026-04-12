/**
 * React hook for i18n translations (G-11 / ART-22).
 *
 * Simple wrapper around the `t` function.  Returns `{ t }` so components
 * can destructure it the same way they would with react-intl or react-i18next.
 *
 * When multi-language support is added, this hook can be expanded to read
 * the active locale from a React context and select the right catalog.
 */

import { t } from "./index";

export function useTranslation() {
  return { t };
}
