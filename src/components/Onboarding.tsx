import React, { useMemo, useRef, useState } from 'react';
import {
  Dimensions,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { Icon, IconName } from './Icon';

const { width } = Dimensions.get('window');

interface Slide {
  icon: IconName;
  title: string;
  body: string;
}

const SLIDES: Slide[] = [
  {
    icon: 'brain',
    title: 'AI that runs offline',
    body: 'Chat with powerful language models that run entirely on your phone — no internet, no accounts, no servers.',
  },
  {
    icon: 'download',
    title: 'Download once, use anywhere',
    body: 'Grab a model from the catalog or paste any GGUF link. Once it’s on your device, it works fully offline.',
  },
  {
    icon: 'shield',
    title: 'Totally private',
    body: 'Your prompts and conversations never leave your phone. Everything happens on-device, for your eyes only.',
  },
];

export function Onboarding({ onDone }: { onDone: () => void }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const scrollRef = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const i = Math.round(e.nativeEvent.contentOffset.x / width);
    if (i !== index) {
      setIndex(i);
    }
  };

  const next = () => {
    if (index >= SLIDES.length - 1) {
      onDone();
      return;
    }
    scrollRef.current?.scrollTo({ x: (index + 1) * width, animated: true });
  };

  const isLast = index === SLIDES.length - 1;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={[styles.topBar, { paddingTop: spacing.sm }]}>
        <Pressable onPress={onDone} hitSlop={10}>
          <Text style={styles.skip}>{isLast ? '' : 'Skip'}</Text>
        </Pressable>
      </View>

      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}>
        {SLIDES.map((s, i) => (
          <View key={i} style={[styles.slide, { width }]}>
            <View style={styles.iconTile}>
              <Icon name={s.icon} size={68} color={colors.onPrimary} />
            </View>
            <Text style={styles.title}>{s.title}</Text>
            <Text style={styles.body}>{s.body}</Text>
          </View>
        ))}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.dots}>
          {SLIDES.map((_, i) => (
            <View
              key={i}
              style={[
                styles.dot,
                i === index ? styles.dotActive : styles.dotInactive,
              ]}
            />
          ))}
        </View>
        <Pressable style={styles.cta} onPress={next}>
          <Text style={styles.ctaText}>
            {isLast ? 'Get started' : 'Next'}
          </Text>
          <Icon
            name={isLast ? 'check' : 'chevronRight'}
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
    skip: { color: colors.textDim, fontSize: 15, fontWeight: '600' },
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
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.xxl,
      shadowColor: colors.primary,
      shadowOpacity: 0.4,
      shadowRadius: 24,
      shadowOffset: { width: 0, height: 12 },
      elevation: 8,
    },
    title: {
      color: colors.text,
      fontSize: 27,
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
    },
    footer: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
    dots: {
      flexDirection: 'row',
      justifyContent: 'center',
      gap: 8,
      marginBottom: spacing.xl,
    },
    dot: { height: 8, borderRadius: 4 },
    dotActive: { width: 22, backgroundColor: colors.primary },
    dotInactive: { width: 8, backgroundColor: colors.border },
    cta: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: colors.primary,
      paddingVertical: spacing.md + 2,
      borderRadius: radius.md,
    },
    ctaText: { color: colors.onPrimary, fontSize: 16, fontWeight: '700' },
  });
