import React, { useMemo, useRef, useState } from 'react';
import {
  Animated,
  Dimensions,
  FlatList,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { radius, shadows, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { GradientFill } from './GradientFill';
import { Icon, IconName } from './Icon';

const { width } = Dimensions.get('window');

interface Slide {
  icon: IconName;
  title: string;
  body: string;
  /** Tiny proof point under the body — makes the promise concrete. */
  proof: string;
}

const SLIDES: Slide[] = [
  {
    icon: 'brain',
    title: 'AI that runs offline',
    body: 'Chat with powerful language models that run entirely on your phone — no internet, no accounts, no servers.',
    proof: 'Works even in airplane mode ✈',
  },
  {
    icon: 'download',
    title: 'Download once,\nuse anywhere',
    body: 'Grab a model from the catalog or paste any GGUF link. Once it’s on your device, it works fully offline.',
    proof: 'Models picked to fit your phone',
  },
  {
    icon: 'shield',
    title: 'Totally private',
    body: 'Your prompts and conversations never leave your phone. Everything happens on-device, for your eyes only.',
    proof: 'Nothing to track. Nothing to leak.',
  },
];

export function Onboarding({
  onDone,
}: {
  /** `goToModels` is true when finished via the final CTA (not skipped). */
  onDone: (goToModels?: boolean) => void;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const scrollRef = useRef<FlatList<Slide> | null>(null);
  const scrollX = useRef(new Animated.Value(0)).current;
  const [index, setIndex] = useState(0);

  const onScroll = Animated.event(
    [{ nativeEvent: { contentOffset: { x: scrollX } } }],
    {
      useNativeDriver: false,
      listener: (e: NativeSyntheticEvent<NativeScrollEvent>) => {
        const i = Math.round(e.nativeEvent.contentOffset.x / width);
        if (i !== index) {
          setIndex(i);
        }
      },
    },
  );

  const isLast = index === SLIDES.length - 1;

  const next = () => {
    if (isLast) {
      onDone(true);
      return;
    }
    scrollRef.current?.scrollToOffset({
      offset: (index + 1) * width,
      animated: true,
    });
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={[styles.topBar, { paddingTop: spacing.sm }]}>
        <Pressable
          onPress={() => onDone(false)}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Skip onboarding">
          <Text style={styles.skip}>{isLast ? '' : 'Skip'}</Text>
        </Pressable>
      </View>

      <Animated.FlatList
        ref={scrollRef as React.Ref<FlatList<Slide>>}
        data={SLIDES}
        keyExtractor={s => s.title}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        renderItem={({ item, index: i }) => {
          const inputRange = [(i - 1) * width, i * width, (i + 1) * width];
          const tileScale = scrollX.interpolate({
            inputRange,
            outputRange: [0.7, 1, 0.7],
            extrapolate: 'clamp',
          });
          const textShift = scrollX.interpolate({
            inputRange,
            outputRange: [width * 0.18, 0, -width * 0.18],
            extrapolate: 'clamp',
          });
          const fade = scrollX.interpolate({
            inputRange,
            outputRange: [0.2, 1, 0.2],
            extrapolate: 'clamp',
          });
          return (
            <View style={[styles.slide, { width }]}>
              <Animated.View
                style={[styles.iconTile, { transform: [{ scale: tileScale }] }]}>
                <GradientFill
                  colors={[colors.gradientStart, colors.gradientEnd]}
                  radius={32}
                />
                <Icon name={item.icon} size={68} color={colors.onPrimary} />
              </Animated.View>
              <Animated.View
                style={{ opacity: fade, transform: [{ translateX: textShift }] }}>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.body}>{item.body}</Text>
                <View style={styles.proofPill}>
                  <Icon name="check" size={14} color={colors.success} />
                  <Text style={styles.proofText}>{item.proof}</Text>
                </View>
              </Animated.View>
            </View>
          );
        }}
      />

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.dots}>
          {SLIDES.map((_, i) => {
            const w = scrollX.interpolate({
              inputRange: [(i - 1) * width, i * width, (i + 1) * width],
              outputRange: [8, 22, 8],
              extrapolate: 'clamp',
            });
            const bg = scrollX.interpolate({
              inputRange: [(i - 1) * width, i * width, (i + 1) * width],
              outputRange: [colors.border, colors.primary, colors.border],
              extrapolate: 'clamp',
            });
            return (
              <Animated.View
                key={i}
                style={[styles.dot, { width: w, backgroundColor: bg }]}
              />
            );
          })}
        </View>
        <Pressable
          style={({ pressed }) => [
            styles.cta,
            pressed && { transform: [{ scale: 0.97 }] },
          ]}
          accessibilityRole="button"
          onPress={next}>
          <Text style={styles.ctaText}>
            {isLast ? 'Pick your first model' : 'Next'}
          </Text>
          <Icon
            name={isLast ? 'sparkles' : 'chevronRight'}
            size={18}
            color={colors.onPrimary}
          />
        </Pressable>
      </View>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    root: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: colors.bg,
      zIndex: 90,
    },
    topBar: {
      height: 44,
      paddingHorizontal: spacing.xl,
      alignItems: 'flex-end',
      justifyContent: 'center',
    },
    skip: {
      color: colors.textDim,
      fontSize: 15,
      fontFamily: fonts.body.semibold,
    },
    slide: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: spacing.xl,
    },
    iconTile: {
      width: 132,
      height: 132,
      borderRadius: 32,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.xxl,
      ...shadows.glow(colors.primary),
    },
    title: {
      color: colors.text,
      fontSize: 28,
      fontFamily: fonts.display.bold,
      letterSpacing: -0.5,
      textAlign: 'center',
      marginBottom: spacing.md,
    },
    body: {
      color: colors.textDim,
      fontSize: 15,
      lineHeight: 23,
      textAlign: 'center',
      maxWidth: 340,
      fontFamily: fonts.body.regular,
    },
    proofPill: {
      flexDirection: 'row',
      alignItems: 'center',
      alignSelf: 'center',
      gap: 6,
      marginTop: spacing.lg,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceAlt,
    },
    proofText: {
      color: colors.textDim,
      fontSize: 13,
      fontFamily: fonts.body.semibold,
    },
    footer: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
    dots: {
      flexDirection: 'row',
      justifyContent: 'center',
      gap: 8,
      marginBottom: spacing.xl,
    },
    dot: { height: 8, borderRadius: 4 },
    cta: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: colors.primary,
      paddingVertical: spacing.md + 2,
      borderRadius: radius.pill,
      ...shadows.glow(colors.primary),
    },
    ctaText: {
      color: colors.onPrimary,
      fontSize: 16,
      fontFamily: fonts.body.bold,
    },
  });
