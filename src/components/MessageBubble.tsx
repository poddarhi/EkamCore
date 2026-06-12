import Clipboard from '@react-native-clipboard/clipboard';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ChatMessage } from '../types';
import { Icon, IconName } from './Icon';
import { TypingDots } from './TypingDots';

/** Small ghost icon button used in the action row under finished AI replies. */
function ActionChip({
  icon,
  label,
  onPress,
  colors,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  colors: ThemeColors;
}) {
  return (
    <Pressable
      onPress={onPress}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        chipStyles.chip,
        pressed && { backgroundColor: colors.surfaceAlt, opacity: 0.85 },
      ]}>
      <Icon name={icon} size={14} color={colors.textDim} />
      <Text style={[chipStyles.chipText, { color: colors.textDim }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const chipStyles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  chipText: { fontSize: 12, fontFamily: fonts.body.semibold },
});

export function MessageBubble({
  message,
  isLast = false,
  onRegenerate,
}: {
  message: ChatMessage;
  /** True for the final message in the thread (enables Retry). */
  isLast?: boolean;
  onRegenerate?: () => void;
}) {
  const { colors } = useTheme();
  const isUser = message.role === 'user';
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const markdownStyles = useMemo(() => makeMarkdownStyles(colors), [colors]);
  const [copied, setCopied] = useState(false);

  const enter = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(enter, {
      toValue: 1,
      duration: 320,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [enter]);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const t = setTimeout(() => setCopied(false), 1400);
    return () => clearTimeout(t);
  }, [copied]);

  const copy = () => {
    Clipboard.setString(message.content);
    setCopied(true);
  };

  const renderBody = () => {
    if (isUser) {
      return <Text style={styles.userText}>{message.content}</Text>;
    }
    if (message.streaming) {
      if (!message.content) {
        return (
          <View style={styles.thinkingRow}>
            <TypingDots color={colors.accent} />
            <Text style={styles.thinkingText}>Thinking…</Text>
          </View>
        );
      }
      return (
        <Text style={styles.text}>
          {message.content}
          <Text style={styles.caret}>▍</Text>
        </Text>
      );
    }
    return <Markdown style={markdownStyles}>{message.content}</Markdown>;
  };

  const showActions = !isUser && !message.streaming && !!message.content;

  return (
    <Animated.View
      style={[
        styles.row,
        isUser ? styles.rowUser : styles.rowAssistant,
        {
          opacity: enter,
          transform: [
            { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) },
            { scale: enter.interpolate({ inputRange: [0, 1], outputRange: [0.96, 1] }) },
          ],
        },
      ]}>
      <View style={isUser ? styles.colUser : styles.colAssistant}>
        <Pressable
          onLongPress={copy}
          delayLongPress={350}
          accessibilityLabel={isUser ? 'Your message' : 'Assistant message'}
          accessibilityHint="Long-press to copy"
          style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
          {renderBody()}
        </Pressable>

        {showActions && (
          <View style={styles.actionRow}>
            <ActionChip
              icon={copied ? 'check' : 'copy'}
              label={copied ? 'Copied' : 'Copy'}
              onPress={copy}
              colors={colors}
            />
            {isLast && onRegenerate ? (
              <ActionChip
                icon="refresh"
                label="Retry"
                onPress={onRegenerate}
                colors={colors}
              />
            ) : null}
            {message.tokensPerSecond ? (
              <Text style={styles.meta}>{message.tokensPerSecond} tok/s</Text>
            ) : null}
          </View>
        )}
        {isUser && copied && (
          <Text style={styles.copiedNote}>Copied</Text>
        )}
      </View>
    </Animated.View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    row: { marginBottom: spacing.md, flexDirection: 'row' },
    rowUser: { justifyContent: 'flex-end' },
    rowAssistant: { justifyContent: 'flex-start' },
    colUser: { maxWidth: '88%', alignItems: 'flex-end' },
    colAssistant: { maxWidth: '88%', alignItems: 'flex-start' },
    bubble: {
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm + 2,
      borderRadius: radius.lg,
    },
    userBubble: {
      backgroundColor: colors.userBubble,
      borderBottomRightRadius: radius.sm,
    },
    aiBubble: {
      backgroundColor: colors.aiBubble,
      borderBottomLeftRadius: radius.sm,
      borderWidth: 1,
      borderColor: colors.border,
    },
    text: {
      color: colors.text,
      fontSize: 15,
      lineHeight: 21,
      fontFamily: fonts.body.regular,
    },
    userText: {
      color: colors.userBubbleText,
      fontSize: 15,
      lineHeight: 21,
      fontFamily: fonts.body.medium,
    },
    caret: { color: colors.accent, fontSize: 12 },
    thinkingRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
    },
    thinkingText: {
      color: colors.textDim,
      fontSize: 13,
      fontFamily: fonts.body.medium,
    },
    actionRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      marginTop: 2,
      marginLeft: spacing.xs,
    },
    meta: {
      color: colors.textFaint,
      fontSize: 11,
      marginLeft: spacing.xs,
      fontFamily: fonts.body.medium,
    },
    copiedNote: {
      color: colors.textFaint,
      fontSize: 11,
      marginTop: 2,
      fontFamily: fonts.body.medium,
    },
  });

const mono = fonts.mono;
const makeMarkdownStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    body: {
      color: colors.text,
      fontSize: 15,
      lineHeight: 22,
      fontFamily: fonts.body.regular,
    },
    paragraph: { marginTop: 0, marginBottom: spacing.sm },
    strong: { fontFamily: fonts.body.bold, color: colors.text },
    em: { fontStyle: 'italic' },
    heading1: {
      color: colors.text,
      fontSize: 20,
      fontFamily: fonts.display.bold,
      marginBottom: spacing.xs,
      marginTop: spacing.xs,
    },
    heading2: {
      color: colors.text,
      fontSize: 18,
      fontFamily: fonts.display.semibold,
      marginBottom: spacing.xs,
      marginTop: spacing.xs,
    },
    heading3: {
      color: colors.text,
      fontSize: 16,
      fontFamily: fonts.display.semibold,
      marginBottom: spacing.xs,
      marginTop: spacing.xs,
    },
    bullet_list: { marginBottom: spacing.sm },
    ordered_list: { marginBottom: spacing.sm },
    list_item: { marginBottom: 2 },
    bullet_list_icon: { color: colors.primary },
    ordered_list_icon: { color: colors.primary },
    // The library defaults these to `flex: 1` (flexBasis 0%), which collapses to
    // ~zero width on iOS inside an auto-width bubble and wraps list text one
    // character per line. Use intrinsic width + shrink so text wraps normally.
    bullet_list_content: {
      flex: undefined,
      flexGrow: 0,
      flexShrink: 1,
      flexBasis: 'auto',
    },
    ordered_list_content: {
      flex: undefined,
      flexGrow: 0,
      flexShrink: 1,
      flexBasis: 'auto',
    },
    code_inline: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: mono,
      fontSize: 13,
      borderRadius: 4,
      paddingHorizontal: 4,
    },
    code_block: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: mono,
      fontSize: 13,
      borderRadius: radius.sm,
      padding: spacing.sm,
      borderWidth: 1,
      borderColor: colors.border,
    },
    fence: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: mono,
      fontSize: 13,
      borderRadius: radius.sm,
      padding: spacing.sm,
      borderWidth: 1,
      borderColor: colors.border,
    },
    blockquote: {
      backgroundColor: colors.surfaceAlt,
      borderLeftWidth: 3,
      borderLeftColor: colors.primary,
      paddingHorizontal: spacing.sm,
      borderRadius: radius.sm,
    },
    link: { color: colors.primary },
    hr: { backgroundColor: colors.border, height: 1 },
    table: { borderColor: colors.border },
    th: { padding: spacing.xs },
    td: { padding: spacing.xs },
  });
