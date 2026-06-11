export interface ThemeColors {
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  primary: string;
  primaryDark: string;
  accent: string;
  onPrimary: string;
  text: string;
  textDim: string;
  textFaint: string;
  success: string;
  danger: string;
  warning: string;
  userBubble: string;
  userBubbleText: string;
  aiBubble: string;
  overlay: string;
  // Gradient stops for the brand mark, primary buttons and hero glow.
  gradientStart: string;
  gradientEnd: string;
  // Three colour stops used by the animated aurora chat backdrop.
  aurora1: string;
  aurora2: string;
  aurora3: string;
}

// "Nebula" — a violet → indigo identity with an electric cyan accent.
export const darkColors: ThemeColors = {
  bg: '#0A0713',
  surface: '#140F22',
  surfaceAlt: '#1E1733',
  border: '#2C2444',
  primary: '#8B5CF6',
  primaryDark: '#6D28D9',
  accent: '#22D3EE',
  onPrimary: '#FFFFFF',
  text: '#F2EEFF',
  textDim: '#A99FC6',
  textFaint: '#6C6090',
  success: '#34D399',
  danger: '#FB7185',
  warning: '#FBBF24',
  userBubble: '#8B5CF6',
  userBubbleText: '#FFFFFF',
  aiBubble: '#181228',
  overlay: 'rgba(7,4,16,0.72)',
  gradientStart: '#A78BFA',
  gradientEnd: '#6366F1',
  aurora1: '#7C3AED',
  aurora2: '#22D3EE',
  aurora3: '#EC4899',
};

export const lightColors: ThemeColors = {
  bg: '#F7F5FF',
  surface: '#FFFFFF',
  surfaceAlt: '#EFEAFB',
  border: '#E3DBF6',
  primary: '#7C3AED',
  primaryDark: '#6D28D9',
  accent: '#0EA5E9',
  onPrimary: '#FFFFFF',
  text: '#1B1535',
  textDim: '#5E5680',
  textFaint: '#968CB4',
  success: '#10B981',
  danger: '#EF4444',
  warning: '#D97706',
  userBubble: '#7C3AED',
  userBubbleText: '#FFFFFF',
  aiBubble: '#FFFFFF',
  overlay: 'rgba(27,21,53,0.42)',
  gradientStart: '#8B5CF6',
  gradientEnd: '#6366F1',
  aurora1: '#A78BFA',
  aurora2: '#67E8F9',
  aurora3: '#F0ABFC',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
  pill: 999,
};

/**
 * Elevation scale — one shadow vocabulary for the whole app instead of
 * ad-hoc per-component values. `glow(color)` is the branded halo used on
 * primary CTAs and the hero logo.
 */
export const shadows = {
  card: {
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  raised: {
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 5,
  },
  overlay: {
    shadowColor: '#000',
    shadowOpacity: 0.22,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
  glow: (color: string) => ({
    shadowColor: color,
    shadowOpacity: 0.45,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 5 },
    elevation: 5,
  }),
} as const;
