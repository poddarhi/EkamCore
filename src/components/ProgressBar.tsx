import React, { useEffect, useRef, useState } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { radius } from '../theme';

/**
 * Smoothly-animated determinate progress bar. The fill eases toward each new
 * value instead of snapping, so chunky download callbacks still read as a
 * continuous motion.
 */
export function ProgressBar({ progress }: { progress: number }) {
  const { colors } = useTheme();
  const pct = Math.max(0, Math.min(1, progress));
  const anim = useRef(new Animated.Value(pct)).current;
  const [trackWidth, setTrackWidth] = useState(0);

  useEffect(() => {
    Animated.timing(anim, {
      toValue: pct,
      duration: 280,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [pct, anim]);

  // Native-driven: render the fill at full width and slide it left, clipped
  // by the rounded track.
  const translateX = anim.interpolate({
    inputRange: [0, 1],
    outputRange: [-trackWidth, 0],
  });

  return (
    <View
      style={[styles.track, { backgroundColor: colors.surfaceAlt }]}
      onLayout={e => setTrackWidth(e.nativeEvent.layout.width)}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(pct * 100) }}>
      {trackWidth > 0 && (
        <Animated.View
          style={[
            styles.fill,
            {
              width: trackWidth,
              backgroundColor: colors.primary,
              transform: [{ translateX }],
            },
          ]}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 6,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: radius.pill,
  },
});
