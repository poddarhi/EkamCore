import React, { useMemo } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { formatBytes } from '../utils/format';
import { Icon, IconName } from './Icon';

export function ChatPlusSheet({
  visible,
  onClose,
  onGoToModels,
}: {
  visible: boolean;
  onClose: () => void;
  onGoToModels: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    models,
    downloadedIds,
    loadedModelId,
    loadingModelId,
    load,
    newConversation,
  } = useApp();

  const downloaded = models.filter(m => downloadedIds.includes(m.id));
  const loadedModel = models.find(m => m.id === loadedModelId);
  const supportsVision = !!loadedModel?.vision;

  const switchModel = (id: string) => {
    if (id === loadedModelId) {
      onClose();
      return;
    }
    const m = models.find(x => x.id === id);
    if (m) {
      load(m);
    }
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />

          {/* Attachments (model-aware). Wired up when a vision model is added. */}
          <Text style={styles.sectionLabel}>Attach</Text>
          <AttachRow
            icon="grid"
            label="Photo"
            sub={supportsVision ? 'Send a photo' : 'Current model can’t see images'}
            disabled={!supportsVision}
            styles={styles}
            colors={colors}
          />
          <AttachRow
            icon="fileText"
            label="File"
            sub="Coming soon"
            disabled
            styles={styles}
            colors={colors}
          />

          {/* In-chat model switcher. */}
          <Text style={styles.sectionLabel}>Model for this chat</Text>
          {downloaded.length === 0 ? (
            <Pressable
              style={styles.row}
              onPress={() => {
                onClose();
                onGoToModels();
              }}>
              <Icon name="download" size={18} color={colors.primary} />
              <Text style={styles.rowLabel}>Download a model to get started</Text>
            </Pressable>
          ) : (
            <ScrollView style={styles.modelList}>
              {downloaded.map(m => {
                const active = m.id === loadedModelId;
                const loading = m.id === loadingModelId;
                return (
                  <Pressable
                    key={m.id}
                    style={[styles.row, active && styles.rowActive]}
                    onPress={() => switchModel(m.id)}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowLabel} numberOfLines={1}>
                        {m.name}
                      </Text>
                      <Text style={styles.rowSub}>
                        {m.params} • {m.quant} • {formatBytes(m.sizeBytes)}
                      </Text>
                    </View>
                    {loading ? (
                      <Text style={styles.loadingText}>Loading…</Text>
                    ) : active ? (
                      <Icon name="check" size={18} color={colors.primary} />
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          )}

          <Pressable
            style={styles.newChat}
            onPress={() => {
              newConversation();
              onClose();
            }}>
            <Icon name="plus" size={18} color={colors.onPrimary} />
            <Text style={styles.newChatText}>New chat</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function AttachRow({
  icon,
  label,
  sub,
  disabled,
  styles,
  colors,
}: {
  icon: IconName;
  label: string;
  sub: string;
  disabled?: boolean;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  return (
    <View style={[styles.row, disabled && styles.rowDisabled]}>
      <Icon
        name={icon}
        size={18}
        color={disabled ? colors.textFaint : colors.text}
      />
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowLabel, disabled && { color: colors.textFaint }]}>
          {label}
        </Text>
        <Text style={styles.rowSub}>{sub}</Text>
      </View>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    root: { flex: 1, justifyContent: 'flex-end' },
    backdrop: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
    },
    sheet: {
      backgroundColor: colors.surface,
      borderTopLeftRadius: radius.lg,
      borderTopRightRadius: radius.lg,
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.xxl,
      paddingTop: spacing.sm,
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: colors.border,
      marginBottom: spacing.md,
    },
    sectionLabel: {
      color: colors.textDim,
      fontSize: 12,
      fontFamily: fonts.body.bold,
      textTransform: 'uppercase',
      letterSpacing: 0.6,
      marginTop: spacing.md,
      marginBottom: spacing.xs,
    },
    modelList: { maxHeight: 260 },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.sm,
      borderRadius: radius.md,
    },
    rowActive: { backgroundColor: colors.surfaceAlt },
    rowDisabled: { opacity: 0.6 },
    rowLabel: { color: colors.text, fontSize: 15, fontFamily: fonts.body.semibold },
    rowSub: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    loadingText: { color: colors.primary, fontSize: 13, fontFamily: fonts.body.semibold },
    newChat: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: colors.primary,
      paddingVertical: spacing.md,
      borderRadius: radius.md,
      marginTop: spacing.lg,
    },
    newChatText: { color: colors.onPrimary, fontSize: 15, fontFamily: fonts.body.bold },
  });
