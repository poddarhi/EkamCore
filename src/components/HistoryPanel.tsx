import React, { useEffect, useMemo, useRef } from 'react';
import {
  Alert,
  Animated,
  Dimensions,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { Icon } from './Icon';

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}

const PANEL_WIDTH = Math.min(330, Dimensions.get('window').width * 0.84);

export function HistoryPanel({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    conversations,
    activeConversationId,
    openConversation,
    deleteConversation,
    newConversation,
  } = useApp();

  const slide = useRef(new Animated.Value(-PANEL_WIDTH)).current;
  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(slide, {
        toValue: visible ? 0 : -PANEL_WIDTH,
        duration: 220,
        useNativeDriver: true,
      }),
      Animated.timing(fade, {
        toValue: visible ? 1 : 0,
        duration: 220,
        useNativeDriver: true,
      }),
    ]).start();
  }, [visible, slide, fade]);

  if (!visible) {
    return null;
  }

  const confirmDelete = (id: string, title: string) => {
    Alert.alert('Delete conversation', `Delete “${title}”?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () => deleteConversation(id),
      },
    ]);
  };

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <Animated.View style={[styles.backdrop, { opacity: fade }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      </Animated.View>

      <Animated.View
        style={[styles.panel, { transform: [{ translateX: slide }] }]}>
        <View style={styles.header}>
          <Text style={styles.heading}>Chats</Text>
          <Pressable onPress={onClose} hitSlop={8} style={styles.iconBtn}>
            <Icon name="close" size={20} color={colors.text} />
          </Pressable>
        </View>

        <Pressable
          style={styles.newBtn}
          onPress={() => {
            newConversation();
            onClose();
          }}>
          <Icon name="plus" size={18} color={colors.onPrimary} />
          <Text style={styles.newBtnText}>New chat</Text>
        </Pressable>

        <FlatList
          data={conversations}
          keyExtractor={c => c.id}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            <Text style={styles.empty}>No conversations yet.</Text>
          }
          renderItem={({ item }) => (
            <Pressable
              style={[
                styles.row,
                item.id === activeConversationId && styles.rowActive,
              ]}
              onPress={() => {
                openConversation(item.id);
                onClose();
              }}
              onLongPress={() => confirmDelete(item.id, item.title)}>
              <View style={styles.rowText}>
                <Text style={styles.rowTitle} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={styles.rowMeta}>
                  {relativeTime(item.updatedAt)} • {item.messageCount} msgs
                </Text>
              </View>
              <Pressable
                hitSlop={8}
                onPress={() => confirmDelete(item.id, item.title)}>
                <Icon name="trash" size={17} color={colors.textFaint} />
              </Pressable>
            </Pressable>
          )}
        />
      </Animated.View>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    backdrop: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.4)',
    },
    panel: {
      position: 'absolute',
      top: 0,
      bottom: 0,
      left: 0,
      width: PANEL_WIDTH,
      backgroundColor: colors.surface,
      borderRightWidth: 1,
      borderRightColor: colors.border,
      paddingTop: 56,
      paddingHorizontal: spacing.md,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: spacing.md,
    },
    heading: {
      color: colors.text,
      fontSize: 22,
      fontFamily: fonts.display.bold,
    },
    iconBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surfaceAlt,
    },
    newBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: colors.primary,
      paddingVertical: spacing.md,
      borderRadius: radius.md,
      marginBottom: spacing.md,
    },
    newBtnText: {
      color: colors.onPrimary,
      fontFamily: fonts.body.bold,
      fontSize: 15,
    },
    listContent: { paddingBottom: spacing.xl },
    empty: {
      color: colors.textFaint,
      fontFamily: fonts.body.regular,
      textAlign: 'center',
      marginTop: spacing.xl,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.sm,
      borderRadius: radius.md,
    },
    rowActive: { backgroundColor: colors.surfaceAlt },
    rowText: { flex: 1 },
    rowTitle: {
      color: colors.text,
      fontSize: 15,
      fontFamily: fonts.body.semibold,
    },
    rowMeta: {
      color: colors.textDim,
      fontSize: 12,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
  });
