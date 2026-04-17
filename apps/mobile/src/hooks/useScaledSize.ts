/**
 * useScaledSize — Dynamic Type / font scale support (S16-007 / FS-179).
 *
 * Reads the system font scale (PixelRatio.getFontScale) and provides
 * a multiplier for all font sizes. Supports 100%–200% scaling.
 *
 * Usage:
 *   const { scale, scaledFontSize } = useScaledSize();
 *   <Text style={{ fontSize: scaledFontSize(15) }}>Hello</Text>
 */

import {useEffect, useState} from 'react';
import {AccessibilityInfo, PixelRatio} from 'react-native';

interface ScaledSizeResult {
  /** System font scale multiplier (1.0 = default). */
  scale: number;
  /** Scale a font size by the system multiplier, clamped to 2x. */
  scaledFontSize: (base: number) => number;
  /** Whether the user has enabled reduced motion. */
  reduceMotion: boolean;
}

export function useScaledSize(): ScaledSizeResult {
  const [scale, setScale] = useState(PixelRatio.getFontScale());
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    // Listen for font scale changes (Dynamic Type)
    // PixelRatio doesn't have a listener, but we re-read on accessibility changes
    const sub = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      (enabled: boolean) => {
        setReduceMotion(enabled);
        setScale(PixelRatio.getFontScale());
      },
    );

    // Check reduce motion on mount
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);

    return () => sub.remove();
  }, []);

  const scaledFontSize = (base: number): number => {
    const clamped = Math.min(scale, 2.0); // Cap at 200%
    return Math.round(base * clamped);
  };

  return {scale, scaledFontSize, reduceMotion};
}
