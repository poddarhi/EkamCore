import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ChatMessage } from '../types';
import { TypingDots } from './TypingDots';

export function MessageBubble({ message }: { message: ChatMessage }) {
  const { colors } = useTheme();
  const isUser = message.role === 'user';
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const markdownStyles = useMemo(() => makeMarkdownStyles(colors), [colors]);

  const enter = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(enter, {
      toValue: 1,
      duration: 320,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [enter]);

  const renderBody = () => {
    if (isUser) {
      return <Text style={styles.userText}>{message.content}</Text>;
    }
    if (message.streaming) {
      if (!message.content) {
        return <TypingDots color={colors.accent} />;
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
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
        {renderBody()}
        {!isUser && !message.streaming && message.tokensPerSecond ? (
          <Text style={styles.meta}>{message.tokensPerSecond} tok/s</Text>
        ) : null}
      </View>
    </Animated.View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    row: { marginBottom: spacing.md, flexDirection: 'row' },
    rowUser: { justifyContent: 'flex-end' },
    rowAssistant: { justifyContent: 'flex-start' },
    bubble: {
      maxWidth: '88%',
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
    meta: {
      color: colors.textFaint,
      fontSize: 11,
      marginTop: spacing.xs,
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
