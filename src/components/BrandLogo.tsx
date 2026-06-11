import React from 'react';
import Svg, {
  Circle,
  Defs,
  LinearGradient,
  Polygon,
  Rect,
  Stop,
} from 'react-native-svg';

/**
 * The EkamCore brand mark — matches the app icon.
 * A chat bubble (chat) holding a shield (secure) with an AI spark (LLM),
 * on an indigo→violet gradient. Convey: "secure, offline AI chat".
 */
export function BrandLogo({
  size = 96,
  withBackground = true,
  radius,
}: {
  size?: number;
  withBackground?: boolean;
  radius?: number;
}) {
  const r = radius ?? size * 0.22;
  const shield =
    '36,30.98 50,29 64,30.98 64,38.9 58.68,59.03 50,62 41.32,59.03 36,38.9';
  const keyStem = '48.7,45 51.3,45 52.3,52.2 47.7,52.2';
  const tail = '35.5,63 47,63 30,74.5';

  return (
    <Svg width={size} height={size} viewBox="0 0 100 100">
      <Defs>
        <LinearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#A78BFA" />
          <Stop offset="1" stopColor="#6366F1" />
        </LinearGradient>
        <LinearGradient id="shield" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#8B5CF6" />
          <Stop offset="1" stopColor="#6D28D9" />
        </LinearGradient>
      </Defs>

      {withBackground && (
        <Rect x="0" y="0" width="100" height="100" rx={(r / size) * 100} fill="url(#bg)" />
      )}

      {/* chat bubble */}
      <Polygon points={tail} fill="#FFFFFF" />
      <Rect x="22.5" y="21.5" width="55" height="45" rx="9" fill="#FFFFFF" />

      {/* shield + keyhole (privacy) */}
      <Polygon points={shield} fill="url(#shield)" />
      <Circle cx="50" cy="43.2" r="3.2" fill="#FFFFFF" />
      <Polygon points={keyStem} fill="#FFFFFF" />
    </Svg>
  );
}
