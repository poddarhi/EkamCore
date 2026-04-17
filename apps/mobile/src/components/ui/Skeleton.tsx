/**
 * Skeleton — animated shimmer placeholder (S16-004).
 */
import React, {useEffect, useRef} from 'react';
import {Animated, StyleSheet, type ViewStyle} from 'react-native';
import {Colors, Radius} from '../../design-system/tokens';

interface Props {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

export function Skeleton({
  width = '100%',
  height = 16,
  borderRadius = Radius.md,
  style,
}: Props) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {toValue: 0.7, duration: 800, useNativeDriver: true}),
        Animated.timing(opacity, {toValue: 0.3, duration: 800, useNativeDriver: true}),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        styles.skeleton,
        {width: width as number, height, borderRadius, opacity},
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  skeleton: {
    backgroundColor: Colors.neutral200,
  },
});
