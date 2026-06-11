import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, useWindowDimensions } from 'react-native';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';
import { useTheme } from '../context/ThemeContext';

/** A single soft radial-gradient glow. */
function Blob({ color, size, id }: { color: string; size: number; id: string }) {
  return (
    <Svg width={size} height={size}>
      <Defs>
        <RadialGradient id={id} cx="50%" cy="50%" r="50%">
          <Stop offset="0" stopColor={color} stopOpacity={0.9} />
          <Stop offset="0.55" stopColor={color} stopOpacity={0.35} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={`url(#${id})`} />
    </Svg>
  );
}

/**
 * Ambient, always-moving aurora behind the chat. Three coloured glows drift and
 * breathe on a slow loop; when `active` (the model is generating) the whole
 * field brightens and swells so the screen visibly "comes alive" as it answers.
 */
export function AuroraBackground({ active = false }: { active?: boolean }) {
  const { colors } = useTheme();
  const { width, height } = useWindowDimensions();
  const big = Math.max(width, height);

  // One driver per blob for organic, out-of-phase drifting (native-driven).
  const d1 = useRef(new Animated.Value(0)).current;
  const d2 = useRef(new Animated.Value(0)).current;
  const d3 = useRef(new Animated.Value(0)).current;
  // Brightens/expands the whole field while the model is generating.
  const energy = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const drift = (val: Animated.Value, duration: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(val, {
            toValue: 1,
            duration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(val, {
            toValue: 0,
            duration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ]),
      );
    const loops = [drift(d1, 7000), drift(d2, 9500), drift(d3, 8200)];
    loops.forEach(l => l.start());
    return () => loops.forEach(l => l.stop());
  }, [d1, d2, d3]);

  useEffect(() => {
    Animated.timing(energy, {
      toValue: active ? 1 : 0,
      duration: active ? 900 : 1400,
      easing: Easing.inOut(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [active, energy]);

  const styles = useMemo(() => makeStyles(), []);

  // Resting opacity is gentle; generating pushes each glow brighter.
  const op = (rest: number, hot: number) =>
    energy.interpolate({ inputRange: [0, 1], outputRange: [rest, hot] });
  const swell = energy.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });

  const blob = (
    driver: Animated.Value,
    color: string,
    id: string,
    size: number,
    from: { x: number; y: number },
    to: { x: number; y: number },
    rest: number,
    hot: number,
  ) => (
    <Animated.View
      style={[
        styles.blobWrap,
        {
          width: size,
          height: size,
          opacity: op(rest, hot),
          transform: [
            {
              translateX: driver.interpolate({
                inputRange: [0, 1],
                outputRange: [from.x, to.x],
              }),
            },
            {
              translateY: driver.interpolate({
                inputRange: [0, 1],
                outputRange: [from.y, to.y],
              }),
            },
            { scale: swell },
          ],
        },
      ]}>
      <Blob color={color} size={size} id={id} />
    </Animated.View>
  );

  return (
    <Animated.View pointerEvents="none" style={styles.root}>
      {blob(
        d1,
        colors.aurora1,
        'aA',
        big * 0.95,
        { x: -big * 0.25, y: -big * 0.18 },
        { x: -big * 0.05, y: big * 0.02 },
        0.5,
        0.85,
      )}
      {blob(
        d2,
        colors.aurora2,
        'aB',
        big * 0.8,
        { x: big * 0.35, y: -big * 0.05 },
        { x: big * 0.12, y: big * 0.15 },
        0.45,
        0.75,
      )}
      {blob(
        d3,
        colors.aurora3,
        'aC',
        big * 0.85,
        { x: -big * 0.05, y: big * 0.45 },
        { x: big * 0.2, y: big * 0.6 },
        0.4,
        0.68,
      )}
    </Animated.View>
  );
}

const makeStyles = () =>
  StyleSheet.create({
    root: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      overflow: 'hidden',
    },
    blobWrap: { position: 'absolute' },
  });
