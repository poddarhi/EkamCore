import React, { useRef } from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

/**
 * An absolutely-positioned linear-gradient layer to drop behind any rounded
 * container (icon tiles, CTAs, hero cards). Uses react-native-svg so we get a
 * true gradient without pulling in a separate gradient-view dependency.
 */
export function GradientFill({
  colors,
  radius = 0,
  start = { x: 0, y: 0 },
  end = { x: 1, y: 1 },
}: {
  colors: [string, string];
  radius?: number;
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}) {
  // Stable, SVG-safe id (useId can emit ":" which breaks url(#…) refs).
  const id = useRef(`grad${Math.random().toString(36).slice(2, 9)}`).current;
  return (
    <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
      <Defs>
        <LinearGradient id={id} x1={start.x} y1={start.y} x2={end.x} y2={end.y}>
          <Stop offset="0" stopColor={colors[0]} />
          <Stop offset="1" stopColor={colors[1]} />
        </LinearGradient>
      </Defs>
      <Rect
        x="0"
        y="0"
        width="100%"
        height="100%"
        rx={radius}
        ry={radius}
        fill={`url(#${id})`}
      />
    </Svg>
  );
}
