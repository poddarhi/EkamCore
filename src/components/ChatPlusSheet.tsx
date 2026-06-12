import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { downloadedVisionModels } from '../services/capabilities';
import { listRemoteModels } from '../services/remote';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { formatBytes } from '../utils/format';
import { Icon, IconName } from './Icon';

export function ChatPlusSheet({
  visible,
  onClose,
  onGoToModels,
  onPickImage,
}: {
  visible: boolean;
  onClose: () => void;
  onGoToModels: () => void;
  /** Called once a vision model is active; source picks the input. */
  onPickImage: (source: 'library' | 'camera') => void;
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
    remoteEndpoints,
    activeRemote,
    selectRemoteModel,
  } = useApp();

  const downloaded = models.filter(m => downloadedIds.includes(m.id));
  const visionModels = downloadedVisionModels(models, downloadedIds);

  const [remoteModels, setRemoteModels] = useState<Record<string, string[]>>({});
  const [loadingRemote, setLoadingRemote] = useState(false);

  // Fetch each connected server's model list when the sheet opens.
  useEffect(() => {
    if (!visible || remoteEndpoints.length === 0) {
      return;
    }
    let cancelled = false;
    setLoadingRemote(true);
    Promise.all(
      remoteEndpoints.map(async ep => [ep.id, await listRemoteModels(ep)] as const),
    ).then(pairs => {
      if (!cancelled) {
        setRemoteModels(Object.fromEntries(pairs));
        setLoadingRemote(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [visible, remoteEndpoints]);

  const switchModel = (id: string) => {
    if (id === loadedModelId && !activeRemote) {
      onClose();
      return;
    }
    const m = models.find(x => x.id === id);
    if (m) {
      load(m);
    }
    onClose();
  };

  const pickRemote = (endpointId: string, model: string) => {
    selectRemoteModel(endpointId, model);
    onClose();
  };

  const [chooserSource, setChooserSource] = useState<null | 'library' | 'camera'>(
    null,
  );

  const ensureActiveThenPick = async (
    modelId: string,
    source: 'library' | 'camera',
  ) => {
    if (modelId !== loadedModelId || activeRemote) {
      const m = models.find(x => x.id === modelId);
      if (m) {
        await load(m); // swaps + initMultimodal; "Loading…" shows via loadingModelId
      }
    }
    onClose();
    onPickImage(source);
  };

  const beginAttach = (source: 'library' | 'camera') => {
    if (activeRemote) {
      return; // remote vision unsupported; rows are disabled in that case
    }
    if (visionModels.length === 0) {
      onClose();
      onGoToModels(); // route to Models to download a vision model
      return;
    }
    if (visionModels.length === 1) {
      ensureActiveThenPick(visionModels[0].id, source);
      return;
    }
    setChooserSource(source); // many → show in-place chooser
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />

          <Text style={styles.sectionLabel}>Attach</Text>
          <AttachRow
            icon="grid"
            label="Photo Library"
            sub={
              activeRemote
                ? 'Not Available On Remote'
                : visionModels.length === 0
                ? 'Get A Vision Model'
                : 'Send A Photo'
            }
            disabled={!!activeRemote}
            onPress={() => beginAttach('library')}
            styles={styles}
            colors={colors}
          />
          <AttachRow
            icon="camera"
            label="Camera"
            sub={activeRemote ? 'Not Available On Remote' : 'Take A Photo'}
            disabled={!!activeRemote}
            onPress={() => beginAttach('camera')}
            styles={styles}
            colors={colors}
          />
          <AttachRow
            icon="fileText"
            label="File"
            sub="Coming Soon"
            disabled
            styles={styles}
            colors={colors}
          />
          {chooserSource && (
            <>
              <Text style={styles.sectionLabel}>Use Which Image Model?</Text>
              {visionModels.map(m => (
                <Pressable
                  key={m.id}
                  style={styles.row}
                  onPress={() => {
                    const src = chooserSource;
                    setChooserSource(null);
                    ensureActiveThenPick(m.id, src);
                  }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>
                    {m.name}
                  </Text>
                </Pressable>
              ))}
            </>
          )}

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
                const active = !activeRemote && m.id === loadedModelId;
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

          {remoteEndpoints.length > 0 && (
            <>
              <Text style={styles.sectionLabel}>Your computers (remote)</Text>
              {loadingRemote && (
                <ActivityIndicator color={colors.primary} style={{ marginVertical: spacing.sm }} />
              )}
              {remoteEndpoints.map(ep => {
                const list = remoteModels[ep.id] ?? [];
                return (
                  <View key={ep.id}>
                    <Text style={styles.epHeader}>{ep.name}</Text>
                    {list.length === 0 && !loadingRemote ? (
                      <Text style={styles.epEmpty}>Not reachable right now</Text>
                    ) : (
                      list.map(model => {
                        const active =
                          activeRemote?.endpointId === ep.id &&
                          activeRemote?.model === model;
                        return (
                          <Pressable
                            key={model}
                            style={[styles.row, active && styles.rowActive]}
                            onPress={() => pickRemote(ep.id, model)}>
                            <Text style={[styles.rowLabel, { flex: 1 }]} numberOfLines={1}>
                              {model}
                            </Text>
                            {active && (
                              <Icon name="check" size={18} color={colors.primary} />
                            )}
                          </Pressable>
                        );
                      })
                    )}
                  </View>
                );
              })}
            </>
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
  onPress,
  styles,
  colors,
}: {
  icon: IconName;
  label: string;
  sub: string;
  disabled?: boolean;
  onPress?: () => void;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  return (
    <Pressable
      style={[styles.row, disabled && styles.rowDisabled]}
      disabled={disabled}
      onPress={onPress}>
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
    </Pressable>
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
    epHeader: {
      color: colors.text,
      fontSize: 13,
      fontFamily: fonts.body.bold,
      marginTop: spacing.sm,
      marginLeft: spacing.sm,
    },
    epEmpty: {
      color: colors.textFaint,
      fontSize: 12.5,
      marginLeft: spacing.sm,
      marginVertical: spacing.xs,
      fontFamily: fonts.body.regular,
    },
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
