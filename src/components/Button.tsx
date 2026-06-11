import React, { useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { radius, shadows, spacing } from '../theme';
import { fonts } from '../typography';
import { Icon, IconName } from './Icon';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

interface Props {
  label: string;
  onPress: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  icon?: IconName;
  style?: ViewStyle;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading,
  disabled,
  icon,
  style,
}: Props) {
  const { colors } = useTheme();
  const isDisabled = disabled || loading;
  const scale = useRef(new Animated.Value(1)).current;

  const pressIn = () =>
    Animated.spring(scale, {
      toValue: 0.96,
      useNativeDriver: true,
      friction: 6,
      tension: 220,
    }).start();
  const pressOut = () =>
    Animated.spring(scale, {
      toValue: 1,
      useNativeDriver: true,
      friction: 5,
      tension: 180,
    }).start();

  const bg: Record<Variant, ViewStyle> = {
    primary: {
      backgroundColor: colors.primary,
      ...(!isDisabled ? shadows.glow(colors.primary) : null),
    },
    secondary: {
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
    },
    danger: {
      backgroundColor: 'transparent',
      borderWidth: 1,
      borderColor: colors.danger,
    },
    ghost: { backgroundColor: 'transparent' },
  };

  const fg: Record<Variant, string> = {
    primary: colors.onPrimary,
    secondary: colors.text,
    danger: colors.danger,
    ghost: colors.text,
  };

  return (
    <Animated.View style={[{ transform: [{ scale }] }, style]}>
      <Pressable
        onPress={onPress}
        onPressIn={pressIn}
        onPressOut={pressOut}
        disabled={isDisabled}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
        style={({ pressed }) => [
          styles.base,
          bg[variant],
          isDisabled && styles.disabled,
          pressed && !isDisabled && styles.pressed,
        ]}>
        {loading ? (
          <ActivityIndicator color={fg[variant]} />
        ) : (
          <View style={styles.content}>
            {icon && <Icon name={icon} size={16} color={fg[variant]} />}
            <Text style={[styles.label, { color: fg[variant] }]}>{label}</Text>
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  base: {
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
  },
  content: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  label: { fontSize: 14, fontFamily: fonts.body.bold },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.92 },
});
