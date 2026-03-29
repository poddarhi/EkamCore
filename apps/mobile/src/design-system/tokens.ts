/** EkamCore design tokens for React Native (mirrors web tokens.css). */

export const Colors = {
  primary: '#1F3864',
  primaryHover: '#162A4D',
  primaryLight: '#2E75B6',
  primarySurface: '#E8EFF8',

  neutral900: '#1A1A1A',
  neutral700: '#404040',
  neutral600: '#666666',
  neutral500: '#888888',
  neutral400: '#AAAAAA',
  neutral200: '#D9D9D9',
  neutral100: '#F2F2F2',
  neutral50: '#F8F8F8',
  white: '#FFFFFF',

  success: '#28A745',
  successSurface: '#E6F4EA',
  warning: '#E6A817',
  warningSurface: '#FFF8E1',
  error: '#DC3545',
  errorSurface: '#FDEDED',
  info: '#0D6EFD',
  infoSurface: '#E7F1FF',
} as const;

/** Spacing (4px base). Index matches token number: sp(4) = 16px. */
export function sp(n: 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16): number {
  return n * 4;
}

export const Radius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 9999,
} as const;

export const Typography = {
  display: {fontSize: 32, lineHeight: 40, fontWeight: '700' as const},
  h1: {fontSize: 24, lineHeight: 32, fontWeight: '700' as const},
  h2: {fontSize: 20, lineHeight: 28, fontWeight: '600' as const},
  h3: {fontSize: 18, lineHeight: 24, fontWeight: '600' as const},
  body: {fontSize: 15, lineHeight: 22, fontWeight: '400' as const},
  small: {fontSize: 13, lineHeight: 18, fontWeight: '400' as const},
  caption: {fontSize: 12, lineHeight: 16, fontWeight: '500' as const},
} as const;

export const ConfidenceBadge = {
  high: {bg: '#E6F4EA', text: '#1B6E2E', border: '#28A745'},
  medium: {bg: '#FFF8E1', text: '#8A6D00', border: '#E6A817'},
  low: {bg: '#F2F2F2', text: '#666666', border: '#AAAAAA'},
} as const;
