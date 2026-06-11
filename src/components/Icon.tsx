import React from 'react';
import Svg, { Circle, Path } from 'react-native-svg';

export type IconName =
  | 'chat'
  | 'models'
  | 'settings'
  | 'send'
  | 'stop'
  | 'download'
  | 'trash'
  | 'check'
  | 'plus'
  | 'close'
  | 'moon'
  | 'sun'
  | 'phone'
  | 'chevronRight'
  | 'bolt'
  | 'brain'
  | 'shield'
  | 'grid'
  | 'mail'
  | 'reply'
  | 'fileText'
  | 'edit'
  | 'calendar'
  | 'star'
  | 'refresh'
  | 'arrowLeft'
  | 'share'
  | 'copy'
  | 'sparkles'
  | 'history'
  | 'search'
  | 'arrowDown';

interface Props {
  name: IconName;
  size?: number;
  color: string;
  strokeWidth?: number;
}

/**
 * Lightweight Feather-style stroked icons drawn with react-native-svg.
 * Keeps the bundle small and avoids the vector-icons font pipeline.
 */
export function Icon({ name, size = 24, color, strokeWidth = 2 }: Props) {
  const common = {
    stroke: color,
    strokeWidth,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    fill: 'none' as const,
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {renderPaths(name, color, common)}
    </Svg>
  );
}

function renderPaths(
  name: IconName,
  color: string,
  c: {
    stroke: string;
    strokeWidth: number;
    strokeLinecap: 'round';
    strokeLinejoin: 'round';
    fill: 'none';
  },
) {
  switch (name) {
    case 'chat':
      return (
        <Path
          {...c}
          d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"
        />
      );
    case 'models':
      return (
        <>
          <Path
            {...c}
            d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"
          />
          <Path {...c} d="M3.27 6.96 12 12.01l8.73-5.05" />
          <Path {...c} d="M12 22.08V12" />
        </>
      );
    case 'settings':
      return (
        <>
          <Path {...c} d="M4 21v-7" />
          <Path {...c} d="M4 10V3" />
          <Path {...c} d="M12 21v-9" />
          <Path {...c} d="M12 8V3" />
          <Path {...c} d="M20 21v-5" />
          <Path {...c} d="M20 12V3" />
          <Path {...c} d="M1 14h6" />
          <Path {...c} d="M9 8h6" />
          <Path {...c} d="M17 16h6" />
        </>
      );
    case 'send':
      return (
        <>
          <Path {...c} d="M12 19V5" />
          <Path {...c} d="M5 12l7-7 7 7" />
        </>
      );
    case 'stop':
      return <Path d="M7 7h10v10H7z" fill={color} stroke={color} strokeWidth={c.strokeWidth} strokeLinejoin="round" />;
    case 'download':
      return (
        <>
          <Path {...c} d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <Path {...c} d="M7 10l5 5 5-5" />
          <Path {...c} d="M12 15V3" />
        </>
      );
    case 'trash':
      return (
        <>
          <Path {...c} d="M3 6h18" />
          <Path {...c} d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <Path {...c} d="M10 11v6" />
          <Path {...c} d="M14 11v6" />
        </>
      );
    case 'check':
      return <Path {...c} d="M20 6 9 17l-5-5" />;
    case 'plus':
      return (
        <>
          <Path {...c} d="M12 5v14" />
          <Path {...c} d="M5 12h14" />
        </>
      );
    case 'close':
      return (
        <>
          <Path {...c} d="M18 6 6 18" />
          <Path {...c} d="M6 6l12 12" />
        </>
      );
    case 'moon':
      return (
        <Path {...c} d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      );
    case 'sun':
      return (
        <>
          <Circle cx={12} cy={12} r={5} {...c} />
          <Path {...c} d="M12 1v2" />
          <Path {...c} d="M12 21v2" />
          <Path {...c} d="M4.22 4.22l1.42 1.42" />
          <Path {...c} d="M18.36 18.36l1.42 1.42" />
          <Path {...c} d="M1 12h2" />
          <Path {...c} d="M21 12h2" />
          <Path {...c} d="M4.22 19.78l1.42-1.42" />
          <Path {...c} d="M18.36 5.64l1.42-1.42" />
        </>
      );
    case 'phone':
      return (
        <>
          <Path {...c} d="M5 2h14a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z" />
          <Path {...c} d="M12 18h.01" />
        </>
      );
    case 'chevronRight':
      return <Path {...c} d="M9 18l6-6-6-6" />;
    case 'bolt':
      return (
        <Path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" fill={color} stroke={color} strokeWidth={1} strokeLinejoin="round" />
      );
    case 'brain':
      return (
        <>
          <Path {...c} d="M9.5 2a3 3 0 0 0-3 3v.5A3.5 3.5 0 0 0 4 9a3.5 3.5 0 0 0 1 2.45A3.5 3.5 0 0 0 6.5 18 3 3 0 0 0 12 17V5a3 3 0 0 0-2.5-3z" />
          <Path {...c} d="M14.5 2a3 3 0 0 1 3 3v.5A3.5 3.5 0 0 1 20 9a3.5 3.5 0 0 1-1 2.45A3.5 3.5 0 0 1 17.5 18 3 3 0 0 1 12 17" />
        </>
      );
    case 'shield':
      return (
        <Path {...c} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      );
    case 'grid':
      return (
        <>
          <Path {...c} d="M4 4h6v6H4z" />
          <Path {...c} d="M14 4h6v6h-6z" />
          <Path {...c} d="M14 14h6v6h-6z" />
          <Path {...c} d="M4 14h6v6H4z" />
        </>
      );
    case 'mail':
      return (
        <>
          <Path
            {...c}
            d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"
          />
          <Path {...c} d="M22 6l-10 7L2 6" />
        </>
      );
    case 'reply':
      return (
        <>
          <Path {...c} d="M9 14L4 9l5-5" />
          <Path {...c} d="M20 20v-7a4 4 0 0 0-4-4H4" />
        </>
      );
    case 'fileText':
      return (
        <>
          <Path
            {...c}
            d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
          />
          <Path {...c} d="M14 2v6h6" />
          <Path {...c} d="M8 13h8" />
          <Path {...c} d="M8 17h8" />
          <Path {...c} d="M8 9h2" />
        </>
      );
    case 'edit':
      return (
        <>
          <Path
            {...c}
            d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
          />
          <Path {...c} d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z" />
        </>
      );
    case 'calendar':
      return (
        <>
          <Path
            {...c}
            d="M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"
          />
          <Path {...c} d="M16 2v4" />
          <Path {...c} d="M8 2v4" />
          <Path {...c} d="M3 10h18" />
        </>
      );
    case 'star':
      return (
        <Path
          {...c}
          d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
        />
      );
    case 'refresh':
      return (
        <>
          <Path {...c} d="M23 4v6h-6" />
          <Path {...c} d="M1 20v-6h6" />
          <Path
            {...c}
            d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
          />
        </>
      );
    case 'arrowLeft':
      return (
        <>
          <Path {...c} d="M19 12H5" />
          <Path {...c} d="M12 19l-7-7 7-7" />
        </>
      );
    case 'share':
      return (
        <>
          <Circle cx={18} cy={5} r={3} {...c} />
          <Circle cx={6} cy={12} r={3} {...c} />
          <Circle cx={18} cy={19} r={3} {...c} />
          <Path {...c} d="M8.59 13.51l6.83 3.98" />
          <Path {...c} d="M15.41 6.51l-6.82 3.98" />
        </>
      );
    case 'copy':
      return (
        <>
          <Path
            {...c}
            d="M9 9h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2V9z"
          />
          <Path
            {...c}
            d="M5 15a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2"
          />
        </>
      );
    case 'sparkles':
      return (
        <>
          <Path
            {...c}
            d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"
          />
          <Path {...c} d="M19 14l.7 1.8L21.5 16.5l-1.8.7L19 19l-.7-1.8L16.5 16.5l1.8-.7z" />
        </>
      );
    case 'history':
      return (
        <>
          <Path {...c} d="M3 3v5h5" />
          <Path {...c} d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
          <Path {...c} d="M12 7v5l4 2" />
        </>
      );
    case 'search':
      return (
        <>
          <Circle cx={11} cy={11} r={8} {...c} />
          <Path {...c} d="M21 21l-4.35-4.35" />
        </>
      );
    case 'arrowDown':
      return (
        <>
          <Path {...c} d="M12 5v14" />
          <Path {...c} d="M19 12l-7 7-7-7" />
        </>
      );
    default:
      return null;
  }
}
