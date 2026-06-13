import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Easing,
  FlatList,
  Image,
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
import { DefaultModelSheet } from '../components/DefaultModelSheet';
import { GradientFill } from '../components/GradientFill';
import { Icon } from '../components/Icon';
import { MessageBubble } from '../components/MessageBubble';
import { launchCamera, launchImageLibrary } from 'react-native-image-picker';
import { persistChatImage } from '../services/download';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, shadows, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

function greetingForNow() {
  const h = new Date().getHours();
  if (h < 5) return 'Working late';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 21) return 'Good evening';
  return 'Good night';
}

/** Animated hero shown before the first message — greeting only. */
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
  onGoToModels: (category?: 'text' | 'image') => void;
  keyboardHeight?: number;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    models,
    loadedModelId,
    loadingModelId,
    downloadedIds,
    messages,
    isGenerating,
    sendMessage,
    regenerate,
    stop,
    newConversation,
    activeRemote,
    defaultModelId,
    needsDefaultChoice,
    setDefaultModel,
    dismissDefaultChoice,
  } = useApp();
  const [text, setText] = useState('');
  const [plusOpen, setPlusOpen] = useState(false);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [showJump, setShowJump] = useState(false);
  const [defaultSheetOpen, setDefaultSheetOpen] = useState(false);
  const listRef = useRef<FlatList>(null);
  // Whether the user is parked near the bottom. Only then do we auto-scroll,
  // so scrolling up to re-read older messages is never interrupted.
  const atBottomRef = useRef(true);
  const jumpAnim = useRef(new Animated.Value(0)).current;

  const loadedModel = models.find(m => m.id === loadedModelId);
  const warmingModel = models.find(m => m.id === loadingModelId);
  const activeLabel = activeRemote ? activeRemote.model : loadedModel?.name;
  const ready = !!loadedModelId || !!activeRemote;
  const isWarming = !ready && !!loadingModelId;
  const hasDownloaded = downloadedIds.length > 0;
  const hasMessages = messages.length > 0;
  const lastId = messages.length ? messages[messages.length - 1].id : null;

  // First launch with several models and no default chosen yet: prompt once.
  useEffect(() => {
    if (needsDefaultChoice) {
      setDefaultSheetOpen(true);
    }
  }, [needsDefaultChoice]);

  useEffect(() => {
    if (messages.length > 0 && atBottomRef.current) {
      requestAnimationFrame(() =>
        listRef.current?.scrollToEnd({ animated: true }),
      );
    }
  }, [messages]);

  useEffect(() => {
    Animated.spring(jumpAnim, {
      toValue: showJump ? 1 : 0,
      useNativeDriver: true,
      friction: 7,
      tension: 90,
    }).start();
  }, [showJump, jumpAnim]);

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
    setShowJump(distanceFromBottom > 240);
  };

  const jumpToLatest = () => {
    atBottomRef.current = true;
    listRef.current?.scrollToEnd({ animated: true });
  };

  const onPickImage = async (source: 'library' | 'camera') => {
    const opts = {
      mediaType: 'photo' as const,
      maxWidth: 1024,
      maxHeight: 1024,
      quality: 0.8 as const,
    };
    const res =
      source === 'camera'
        ? await launchCamera(opts)
        : await launchImageLibrary(opts);
    if (res.didCancel || res.errorCode || !res.assets?.[0]?.uri) {
      return;
    }
    const imageId =
      Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    const persisted = await persistChatImage(res.assets[0].uri, imageId);
    setPendingImage(persisted);
  };

  const send = (value: string) => {
    atBottomRef.current = true;
    sendMessage(value, pendingImage ?? undefined);
    setPendingImage(null);
  };

  const onSend = () => {
    const value = text;
    setText('');
    send(value);
  };

  const defaultSheet = (
    <DefaultModelSheet
      visible={defaultSheetOpen}
      currentId={defaultModelId}
      allowSkip
      onPick={id => {
        setDefaultModel(id);
        setDefaultSheetOpen(false);
      }}
      onClose={() => {
        dismissDefaultChoice();
        setDefaultSheetOpen(false);
      }}
    />
  );

  if (!ready) {
    // Auto-loading the default model on launch.
    if (isWarming) {
      return (
        <View style={styles.empty}>
          <AuroraBackground active />
          <View style={styles.emptyIcon}>
            <GradientFill
              colors={[colors.gradientStart, colors.gradientEnd]}
              radius={radius.lg + 8}
            />
            <Icon name="bolt" size={40} color={colors.onPrimary} />
          </View>
          <Text style={styles.emptyTitle}>Warming up</Text>
          <Text style={styles.emptyText}>
            Loading {warmingModel?.name ?? 'your model'} into memory — this
            takes a few seconds the first time.
          </Text>
          <ActivityIndicator
            color={colors.primary}
            style={{ marginTop: spacing.lg }}
          />
        </View>
      );
    }

    // Has models but none active — invite the user to pick one to start.
    if (hasDownloaded) {
      return (
        <View style={styles.empty}>
          <AuroraBackground active={false} />
          <View style={styles.emptyIcon}>
            <GradientFill
              colors={[colors.gradientStart, colors.gradientEnd]}
              radius={radius.lg + 8}
            />
            <Icon name="sparkles" size={40} color={colors.onPrimary} />
          </View>
          <Text style={styles.emptyTitle}>Ready when you are</Text>
          <Text style={styles.emptyText}>
            Pick the model you'd like to chat with. We'll remember it for next
            time.
          </Text>
          <Pressable
            style={({ pressed }) => [
              styles.emptyBtn,
              pressed && { transform: [{ scale: 0.97 }] },
            ]}
            accessibilityRole="button"
            onPress={() => setDefaultSheetOpen(true)}>
            <Icon name="bolt" size={18} color={colors.onPrimary} />
            <Text style={styles.emptyBtnText}>Choose a model</Text>
          </Pressable>
          {defaultSheet}
        </View>
      );
    }

    // No models at all — send the user to the catalog.
    return (
      <View style={styles.empty}>
        <AuroraBackground active={false} />
        <View style={styles.emptyIcon}>
          <GradientFill
            colors={[colors.gradientStart, colors.gradientEnd]}
            radius={radius.lg + 8}
          />
          <Icon name="brain" size={42} color={colors.onPrimary} />
        </View>
        <Text style={styles.emptyTitle}>Let's get you a model</Text>
        <Text style={styles.emptyText}>
          Pick a model made for your phone, download it once, and chat
          privately — even in airplane mode.
        </Text>
        <Pressable
          style={({ pressed }) => [
            styles.emptyBtn,
            pressed && { transform: [{ scale: 0.97 }] },
          ]}
          accessibilityRole="button"
          onPress={() => onGoToModels()}>
          <Icon name="models" size={18} color={colors.onPrimary} />
          <Text style={styles.emptyBtnText}>Choose your model</Text>
        </Pressable>
        <Text style={styles.emptyFootnote}>
          One Download • Works Offline Forever
        </Text>
      </View>
    );
  }

  const canSend = !!text.trim() || !!pendingImage;

  return (
    <View style={styles.container}>
      <AuroraBackground active={isGenerating} />

      {/* Model pill — the current brain, always visible and tappable. */}
      <View style={styles.statusBar}>
        <Pressable
          onPress={() => setPlusOpen(true)}
          accessibilityRole="button"
          accessibilityLabel={`Current model: ${activeLabel ?? 'none'}. Tap to switch.`}
          style={({ pressed }) => [
            styles.modelPill,
            pressed && { opacity: 0.85 },
          ]}>
          <View
            style={[
              styles.statusDot,
              { backgroundColor: activeRemote ? colors.accent : colors.success },
            ]}
          />
          <Text style={styles.statusText} numberOfLines={1}>
            {activeLabel ?? 'Model'}
          </Text>
          <Text style={styles.statusKind}>
            {activeRemote ? 'Remote' : 'On-Device'}
          </Text>
          <Icon name="chevronRight" size={14} color={colors.textFaint} />
        </Pressable>
        <View style={{ flex: 1 }} />
        {hasMessages && (
          <Pressable
            onPress={newConversation}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="New chat"
            style={styles.clearBtn}>
            <Icon name="plus" size={15} color={colors.primary} />
            <Text style={styles.clear}>New</Text>
          </Pressable>
        )}
      </View>

      {hasMessages ? (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={m => m.id}
          renderItem={({ item }) => (
            <MessageBubble
              message={item}
              isLast={item.id === lastId}
              onRegenerate={isGenerating ? undefined : regenerate}
            />
          )}
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

      {/* Jump back to the latest message after scrolling up. */}
      <Animated.View
        pointerEvents={showJump ? 'auto' : 'none'}
        style={[
          styles.jumpWrap,
          keyboardHeight > 0 ? { bottom: keyboardHeight + 86 } : null,
          {
            opacity: jumpAnim,
            transform: [
              { scale: jumpAnim },
              {
                translateY: jumpAnim.interpolate({
                  inputRange: [0, 1],
                  outputRange: [12, 0],
                }),
              },
            ],
          },
        ]}>
        <Pressable
          onPress={jumpToLatest}
          accessibilityRole="button"
          accessibilityLabel="Scroll to latest message"
          style={styles.jumpBtn}>
          <Icon name="arrowDown" size={18} color={colors.text} />
        </Pressable>
      </Animated.View>

      <View
        style={[
          styles.inputWrap,
          keyboardHeight > 0
            ? { paddingBottom: keyboardHeight + spacing.sm }
            : null,
        ]}>
        {pendingImage && (
          <View style={styles.pendingImageRow}>
            <Image
              source={{ uri: `file://${pendingImage}` }}
              style={styles.pendingThumb}
            />
            <Pressable onPress={() => setPendingImage(null)} hitSlop={8}>
              <Icon name="close" size={16} color={colors.textDim} />
            </Pressable>
          </View>
        )}
        <View style={styles.inputPill}>
          <Pressable
            style={styles.leadBtn}
            hitSlop={6}
            accessibilityRole="button"
            accessibilityLabel="Attachments and model options"
            onPress={() => setPlusOpen(true)}>
            <Icon name="plus" size={20} color={colors.textDim} />
          </Pressable>

          <TextInput
            style={styles.input}
            placeholder={`Ask ${activeLabel ?? 'anything'}`}
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
              accessibilityRole="button"
              accessibilityLabel="Stop generating"
              onPress={stop}>
              <Icon name="stop" size={18} color={colors.onPrimary} />
            </Pressable>
          ) : (
            <Pressable
              style={({ pressed }) => [
                styles.sendBtn,
                !canSend && styles.sendDisabled,
                pressed && canSend && styles.btnPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Send message"
              onPress={onSend}
              disabled={!canSend}>
              <Icon name="send" size={19} color={colors.onPrimary} />
            </Pressable>
          )}
        </View>
        {!keyboardHeight && (
          <Text style={styles.footNote}>
            {activeRemote
              ? 'Replies Come From Your Own Computer'
              : 'Runs Fully On-Device • Your Chats Stay Private'}
          </Text>
        )}
      </View>

      <ChatPlusSheet
        visible={plusOpen}
        onClose={() => setPlusOpen(false)}
        onGoToModels={onGoToModels}
        onPickImage={onPickImage}
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
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      gap: spacing.sm,
    },
    modelPill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingLeft: spacing.md,
      paddingRight: spacing.sm,
      paddingVertical: 7,
      borderRadius: radius.pill,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      maxWidth: '78%',
      ...shadows.card,
    },
    statusDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
    },
    statusText: {
      color: colors.text,
      fontSize: 13,
      fontFamily: fonts.body.semibold,
      flexShrink: 1,
    },
    statusKind: {
      color: colors.textFaint,
      fontSize: 12,
      fontFamily: fonts.body.medium,
    },
    clearBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      paddingHorizontal: spacing.sm,
      paddingVertical: 6,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceAlt,
    },
    clear: { color: colors.primary, fontSize: 13, fontFamily: fonts.body.semibold },
    listContent: { padding: spacing.lg, paddingTop: spacing.sm },

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
      ...shadows.glow(colors.primary),
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
    // Jump-to-latest
    jumpWrap: {
      position: 'absolute',
      right: spacing.lg,
      bottom: 96,
    },
    jumpBtn: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
      ...shadows.raised,
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
      ...shadows.raised,
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
      ...shadows.glow(colors.primary),
    },
    sendDisabled: { backgroundColor: colors.surfaceAlt, shadowOpacity: 0, elevation: 0 },
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
      width: 92,
      height: 92,
      borderRadius: radius.lg + 8,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: spacing.lg,
      ...shadows.glow(colors.primary),
    },
    emptyTitle: {
      color: colors.text,
      fontSize: 24,
      fontFamily: fonts.display.bold,
      letterSpacing: -0.4,
    },
    emptyText: {
      color: colors.textDim,
      fontSize: 14.5,
      textAlign: 'center',
      marginTop: spacing.sm,
      lineHeight: 21,
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
      paddingVertical: spacing.md + 2,
      borderRadius: radius.pill,
      ...shadows.glow(colors.primary),
    },
    emptyBtnText: {
      color: colors.onPrimary,
      fontFamily: fonts.body.bold,
      fontSize: 15,
    },
    emptyFootnote: {
      color: colors.textFaint,
      fontSize: 12,
      marginTop: spacing.md,
      fontFamily: fonts.body.medium,
    },
    pendingImageRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.md,
      paddingBottom: spacing.sm,
    },
    pendingThumb: {
      width: 48,
      height: 48,
      borderRadius: radius.sm,
    },
  });
