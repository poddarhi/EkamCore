import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Animated,
  Dimensions,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ConversationMeta } from '../types';
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

/** Bucket label used to group the list by recency. */
function dateBucket(ts: number): string {
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  if (ts >= startOfToday) return 'Today';
  if (ts >= startOfToday - 86400000) return 'Yesterday';
  if (ts >= startOfToday - 6 * 86400000) return 'Previous 7 days';
  return 'Earlier';
}

type ListEntry =
  | { kind: 'header'; key: string; label: string }
  | { kind: 'row'; key: string; conv: ConversationMeta };

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
    renameConversation,
    newConversation,
  } = useApp();

  // Holds the conversation currently being renamed (null = modal closed).
  const [renaming, setRenaming] = useState<{ id: string; text: string } | null>(
    null,
  );
  const [query, setQuery] = useState('');

  // Filter by title, then weave in date-bucket headers (list is already
  // sorted newest-first by the context).
  const entries = useMemo<ListEntry[]>(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? conversations.filter(c => c.title.toLowerCase().includes(q))
      : conversations;
    const out: ListEntry[] = [];
    let lastBucket: string | null = null;
    for (const c of filtered) {
      const bucket = dateBucket(c.updatedAt);
      if (bucket !== lastBucket) {
        out.push({ kind: 'header', key: `h-${bucket}`, label: bucket });
        lastBucket = bucket;
      }
      out.push({ kind: 'row', key: c.id, conv: c });
    }
    return out;
  }, [conversations, query]);

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

  const commitRename = () => {
    if (!renaming) {
      return;
    }
    const title = renaming.text.trim();
    if (title) {
      renameConversation(renaming.id, title);
    }
    setRenaming(null);
  };

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
          accessibilityRole="button"
          onPress={() => {
            newConversation();
            onClose();
          }}>
          <Icon name="plus" size={18} color={colors.onPrimary} />
          <Text style={styles.newBtnText}>New chat</Text>
        </Pressable>

        {conversations.length > 0 && (
          <View style={styles.searchBox}>
            <Icon name="search" size={16} color={colors.textFaint} />
            <TextInput
              style={styles.searchInput}
              placeholder="Search chats"
              placeholderTextColor={colors.textFaint}
              value={query}
              onChangeText={setQuery}
              autoCorrect={false}
              accessibilityLabel="Search chats"
            />
            {query.length > 0 && (
              <Pressable hitSlop={8} onPress={() => setQuery('')}>
                <Icon name="close" size={15} color={colors.textFaint} />
              </Pressable>
            )}
          </View>
        )}

        <FlatList
          data={entries}
          keyExtractor={e => e.key}
          contentContainerStyle={styles.listContent}
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={
            <View style={styles.emptyWrap}>
              <Icon name="chat" size={28} color={colors.textFaint} />
              <Text style={styles.empty}>
                {query
                  ? 'No chats match your search.'
                  : 'Your conversations will appear here.'}
              </Text>
            </View>
          }
          renderItem={({ item }) => {
            if (item.kind === 'header') {
              return <Text style={styles.groupHeader}>{item.label}</Text>;
            }
            const conv = item.conv;
            const active = conv.id === activeConversationId;
            return (
              <Pressable
                style={[styles.row, active && styles.rowActive]}
                onPress={() => {
                  openConversation(conv.id);
                  onClose();
                }}
                onLongPress={() => confirmDelete(conv.id, conv.title)}>
                {active && <View style={styles.activeBar} />}
                <View style={styles.rowText}>
                  <Text
                    style={[styles.rowTitle, active && { color: colors.primary }]}
                    numberOfLines={1}>
                    {conv.title}
                  </Text>
                  <Text style={styles.rowMeta}>
                    {relativeTime(conv.updatedAt)} • {conv.messageCount} msgs
                  </Text>
                </View>
                <Pressable
                  hitSlop={8}
                  style={styles.rowAction}
                  accessibilityLabel="Rename chat"
                  onPress={() => setRenaming({ id: conv.id, text: conv.title })}>
                  <Icon name="edit" size={16} color={colors.textFaint} />
                </Pressable>
                <Pressable
                  hitSlop={8}
                  style={styles.rowAction}
                  accessibilityLabel="Delete chat"
                  onPress={() => confirmDelete(conv.id, conv.title)}>
                  <Icon name="trash" size={17} color={colors.textFaint} />
                </Pressable>
              </Pressable>
            );
          }}
        />
      </Animated.View>

      <Modal
        visible={renaming !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setRenaming(null)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setRenaming(null)}>
          <Pressable style={styles.modalCard} onPress={() => {}}>
            <Text style={styles.modalTitle}>Rename chat</Text>
            <TextInput
              style={styles.modalInput}
              value={renaming?.text ?? ''}
              onChangeText={t =>
                setRenaming(prev => (prev ? { ...prev, text: t } : prev))
              }
              placeholder="Conversation name"
              placeholderTextColor={colors.textFaint}
              autoFocus
              returnKeyType="done"
              onSubmitEditing={commitRename}
            />
            <View style={styles.modalRow}>
              <Pressable
                style={[styles.modalBtn, styles.modalCancel]}
                onPress={() => setRenaming(null)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable
                style={[styles.modalBtn, styles.modalSave]}
                onPress={commitRename}>
                <Text style={styles.modalSaveText}>Save</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
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
    searchBox: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      marginBottom: spacing.md,
      height: 40,
    },
    searchInput: {
      flex: 1,
      color: colors.text,
      fontSize: 14,
      fontFamily: fonts.body.regular,
      paddingVertical: 0,
    },
    groupHeader: {
      color: colors.textFaint,
      fontSize: 11.5,
      fontFamily: fonts.body.bold,
      textTransform: 'uppercase',
      letterSpacing: 0.8,
      marginTop: spacing.md,
      marginBottom: spacing.xs,
      paddingHorizontal: spacing.sm,
    },
    emptyWrap: {
      alignItems: 'center',
      gap: spacing.sm,
      marginTop: spacing.xxl,
    },
    empty: {
      color: colors.textFaint,
      fontFamily: fonts.body.regular,
      textAlign: 'center',
      maxWidth: 220,
      lineHeight: 19,
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
    activeBar: {
      width: 3,
      alignSelf: 'stretch',
      borderRadius: 2,
      backgroundColor: colors.primary,
    },
    rowText: { flex: 1 },
    rowAction: {
      width: 30,
      height: 30,
      alignItems: 'center',
      justifyContent: 'center',
    },
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
    modalBackdrop: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.5)',
      alignItems: 'center',
      justifyContent: 'center',
      padding: spacing.xl,
    },
    modalCard: {
      width: '100%',
      maxWidth: 360,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      padding: spacing.lg,
    },
    modalTitle: {
      color: colors.text,
      fontSize: 18,
      fontFamily: fonts.display.bold,
      marginBottom: spacing.md,
    },
    modalInput: {
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      color: colors.text,
      fontSize: 16,
      fontFamily: fonts.body.regular,
      backgroundColor: colors.bg,
    },
    modalRow: {
      flexDirection: 'row',
      justifyContent: 'flex-end',
      gap: spacing.sm,
      marginTop: spacing.lg,
    },
    modalBtn: {
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      borderRadius: radius.md,
    },
    modalCancel: { backgroundColor: colors.surfaceAlt },
    modalCancelText: {
      color: colors.text,
      fontFamily: fonts.body.semibold,
      fontSize: 15,
    },
    modalSave: { backgroundColor: colors.primary },
    modalSaveText: {
      color: colors.onPrimary,
      fontFamily: fonts.body.bold,
      fontSize: 15,
    },
  });
