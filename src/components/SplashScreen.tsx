import React, { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { spacing } from '../theme';
import { fonts } from '../typography';
import { BrandLogo } from './BrandLogo';

export function SplashScreen({ onFinish }: { onFinish: () => void }) {
  const { colors } = useTheme();
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.8)).current;
  const fade = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: 450,
        useNativeDriver: true,
      }),
      Animated.spring(scale, {
        toValue: 1,
        friction: 6,
        tension: 80,
        useNativeDriver: true,
      }),
    ]).start();

    const t = setTimeout(() => {
      Animated.timing(fade, {
        toValue: 0,
        duration: 380,
        easing: Easing.in(Easing.ease),
        useNativeDriver: true,
      }).start(() => onFinish());
    }, 1400);

    return () => clearTimeout(t);
  }, [opacity, scale, fade, onFinish]);

  return (
    <Animated.View
      style={[styles.root, { backgroundColor: colors.bg, opacity: fade }]}>
      <Animated.View
        style={[styles.logo, { opacity, transform: [{ scale }] }]}>
        <BrandLogo size={108} />
      </Animated.View>
      <Animated.Text style={[styles.title, { color: colors.text, opacity }]}>
        EkamCore
      </Animated.Text>
      <Animated.Text style={[styles.tag, { color: colors.textDim, opacity }]}>
        Private AI, fully on your device
      </Animated.Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  },
  logo: {
    marginBottom: spacing.xl,
    shadowColor: '#8B5CF6',
    shadowOpacity: 0.5,
    shadowRadius: 28,
    shadowOffset: { width: 0, height: 12 },
  },
  title: { fontSize: 31, fontFamily: fonts.display.bold, letterSpacing: 0.3 },
  tag: { fontSize: 14, marginTop: spacing.xs, fontFamily: fonts.body.medium },
});
