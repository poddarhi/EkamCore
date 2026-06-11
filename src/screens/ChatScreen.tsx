import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { AuroraBackground } from '../components/AuroraBackground';
import { BrandLogo } from '../components/BrandLogo';
import { ChatPlusSheet } from '../components/ChatPlusSheet';
import { Icon } from '../components/Icon';
import { MessageBubble } from '../components/MessageBubble';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

function greetingForNow() {
  const h = new Date().getHours();
  if (h < 5) return 'Working late';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 21) return 'Good evening';
  return 'Good night';
}

/** Animated hero shown before the first message — Gemini-style landing. */
function LandingHero({ colors }: { colors: ThemeColors }) {
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const fade = useRef(new Animated.Value(0)).current;
  const rise = useRef(new Animated.Value(24)).current;
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fade, {
        toValue: 1,
        duration: 600,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.timing(rise, {
        toValue: 0,
        duration: 600,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();

    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1800,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 1800,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    ).start();
  }, [fade, rise, pulse]);

  const logoScale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 1.08],
  });
  const logoTranslate = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -6],
  });

  return (
    <Animated.View
      style={[
        styles.hero,
        { opacity: fade, transform: [{ translateY: rise }] },
      ]}>
      <Animated.View
        style={[
          styles.logoSlot,
          { transform: [{ scale: logoScale }, { translateY: logoTranslate }] },
        ]}>
        <BrandLogo size={76} />
      </Animated.View>

      <Text style={styles.greetingSmall}>{greetingForNow()},</Text>
      <Text style={styles.greetingBig}>What's on your mind?</Text>
    </Animated.View>
  );
}

export function ChatScreen({
  onGoToModels,
  keyboardHeight = 0,
}: {
  onGoToModels: () => void;
  keyboardHeight?: number;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    models,
    loadedModelId,
    messages,
    isGenerating,
    sendMessage,
    stop,
    newConversation,
  } = useApp();
  const [text, setText] = useState('');
  const [plusOpen, setPlusOpen] = useState(false);
  const listRef = useRef<FlatList>(null);
  // Whether the user is parked near the bottom. Only then do we auto-scroll,
  // so scrolling up to re-read older messages is never interrupted.
  const atBottomRef = useRef(true);

  const loadedModel = models.find(m => m.id === loadedModelId);
  const hasMessages = messages.length > 0;

  useEffect(() => {
    if (messages.length > 0 && atBottomRef.current) {
      requestAnimationFrame(() =>
        listRef.current?.scrollToEnd({ animated: true }),
      );
    }
  }, [messages]);

  const onScroll = (e: {
    nativeEvent: {
      contentOffset: { y: number };
      contentSize: { height: number };
      layoutMeasurement: { height: number };
    };
  }) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    const distanceFromBottom =
      contentSize.height - (contentOffset.y + layoutMeasurement.height);
    atBottomRef.current = distanceFromBottom < 80;
  };

  const onSend = () => {
    const value = text;
    setText('');
    atBottomRef.current = true;
    sendMessage(value);
  };

  if (!loadedModelId) {
    return (
      <View style={styles.empty}>
        <View style={styles.emptyIcon}>
          <Icon name="brain" size={40} color={colors.primary} />
        </View>
        <Text style={styles.emptyTitle}>No model loaded</Text>
        <Text style={styles.emptyText}>
          Head to the Models tab, download a model, then tap “Load” to start
          chatting offline.
        </Text>
        <Pressable style={styles.emptyBtn} onPress={onGoToModels}>
          <Icon name="models" size={18} color={colors.onPrimary} />
          <Text style={styles.emptyBtnText}>Go to Models</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <AuroraBackground active={isGenerating} />
      {hasMessages && (
        <View style={styles.statusBar}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText} numberOfLines={1}>
            {loadedModel?.name ?? 'Model'} • on-device
          </Text>
          <Pressable onPress={newConversation} hitSlop={8} style={styles.clearBtn}>
            <Icon name="plus" size={15} color={colors.primary} />
            <Text style={styles.clear}>New</Text>
          </Pressable>
        </View>
      )}

      {hasMessages ? (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={m => m.id}
          renderItem={({ item }) => <MessageBubble message={item} />}
          contentContainerStyle={styles.listContent}
          keyboardDismissMode="interactive"
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={100}
        />
      ) : (
        <View style={styles.heroWrap}>
          <LandingHero colors={colors} />
        </View>
      )}

      <View
        style={[
          styles.inputWrap,
          keyboardHeight > 0
            ? { paddingBottom: keyboardHeight + spacing.sm }
            : null,
        ]}>
        <View style={styles.inputPill}>
          <Pressable
            style={styles.leadBtn}
            hitSlop={6}
            onPress={() => setPlusOpen(true)}>
            <Icon name="plus" size={20} color={colors.textDim} />
          </Pressable>

          <TextInput
            style={styles.input}
            placeholder={`Ask ${loadedModel?.name ?? 'anything'}`}
            placeholderTextColor={colors.textFaint}
            value={text}
            onChangeText={setText}
            multiline
          />

          {isGenerating ? (
            <Pressable
              style={({ pressed }) => [
                styles.sendBtn,
                styles.stopBtn,
                pressed && styles.btnPressed,
              ]}
              onPress={stop}>
              <Icon name="stop" size={18} color={colors.onPrimary} />
            </Pressable>
          ) : (
            <Pressable
              style={({ pressed }) => [
                styles.sendBtn,
                !text.trim() && styles.sendDisabled,
                pressed && !!text.trim() && styles.btnPressed,
              ]}
              onPress={onSend}
              disabled={!text.trim()}>
              <Icon name="send" size={19} color={colors.onPrimary} />
            </Pressable>
          )}
        </View>
        {!keyboardHeight && (
          <Text style={styles.footNote}>
            Runs fully on-device • your chats stay private
          </Text>
        )}
      </View>

      <ChatPlusSheet
        visible={plusOpen}
        onClose={() => setPlusOpen(false)}
        onGoToModels={onGoToModels}
      />
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    statusBar: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
      gap: spacing.sm,
    },
    statusDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: colors.success,
    },
    statusText: {
      color: colors.textDim,
      fontSize: 13,
      flex: 1,
      fontFamily: fonts.body.medium,
    },
    clearBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      paddingHorizontal: spacing.sm,
      paddingVertical: 4,
      borderRadius: radius.md,
      backgroundColor: colors.surfaceAlt,
    },
    clear: { color: colors.primary, fontSize: 13, fontFamily: fonts.body.semibold },
    listContent: { padding: spacing.lg },

    // Landing hero
    heroWrap: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: spacing.xl,
    },
    hero: { alignItems: 'center' },
    logoSlot: {
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.xl,
      shadowColor: colors.primary,
      shadowOpacity: 0.35,
      shadowRadius: 18,
      shadowOffset: { width: 0, height: 8 },
    },
    greetingSmall: {
      color: colors.textDim,
      fontSize: 22,
      fontFamily: fonts.display.medium,
      textAlign: 'center',
    },
    greetingBig: {
      color: colors.text,
      fontSize: 31,
      fontFamily: fonts.display.bold,
      textAlign: 'center',
      marginTop: 4,
      letterSpacing: -0.6,
    },

    // Input
    inputWrap: {
      paddingHorizontal: spacing.md,
      paddingTop: spacing.sm,
      paddingBottom: spacing.md,
      backgroundColor: 'transparent',
    },
    inputPill: {
      flexDirection: 'row',
      alignItems: 'flex-end',
      backgroundColor: colors.surface,
      borderRadius: 28,
      borderWidth: 1,
      borderColor: colors.border,
      paddingLeft: spacing.sm,
      paddingRight: 6,
      paddingVertical: 6,
      gap: spacing.xs,
      shadowColor: '#000',
      shadowOpacity: 0.12,
      shadowRadius: 12,
      shadowOffset: { width: 0, height: 4 },
      elevation: 3,
    },
    leadBtn: {
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: 'center',
      justifyContent: 'center',
    },
    input: {
      flex: 1,
      maxHeight: 120,
      minHeight: 40,
      paddingHorizontal: spacing.xs,
      paddingTop: Platform.OS === 'ios' ? spacing.sm + 2 : spacing.sm,
      paddingBottom: spacing.sm,
      color: colors.text,
      fontSize: 16,
      fontFamily: fonts.body.regular,
    },
    sendBtn: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
      shadowColor: colors.primary,
      shadowOpacity: 0.5,
      shadowRadius: 10,
      shadowOffset: { width: 0, height: 4 },
      elevation: 4,
    },
    sendDisabled: { backgroundColor: colors.surfaceAlt },
    stopBtn: { backgroundColor: colors.danger },
    btnPressed: { transform: [{ scale: 0.88 }], opacity: 0.9 },
    footNote: {
      color: colors.textFaint,
      fontSize: 11,
      textAlign: 'center',
      marginTop: spacing.sm,
      fontFamily: fonts.body.medium,
    },

    // No model
    empty: {
      flex: 1,
      backgroundColor: colors.bg,
      alignItems: 'center',
      justifyContent: 'center',
      padding: spacing.xl,
    },
    emptyIcon: {
      width: 88,
      height: 88,
      borderRadius: radius.lg + 4,
      backgroundColor: colors.surfaceAlt,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.lg,
    },
    emptyTitle: {
      color: colors.text,
      fontSize: 21,
      fontFamily: fonts.display.bold,
    },
    emptyText: {
      color: colors.textDim,
      fontSize: 14,
      textAlign: 'center',
      marginTop: spacing.sm,
      lineHeight: 20,
      maxWidth: 320,
      fontFamily: fonts.body.regular,
    },
    emptyBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      marginTop: spacing.xl,
      backgroundColor: colors.primary,
      paddingHorizontal: spacing.xl,
      paddingVertical: spacing.md,
      borderRadius: radius.md,
    },
    emptyBtnText: {
      color: colors.onPrimary,
      fontFamily: fonts.body.bold,
      fontSize: 15,
    },
  });
