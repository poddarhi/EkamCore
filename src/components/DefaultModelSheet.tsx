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
import { radius, shadows, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { formatBytes, quantLabel } from '../utils/format';
import { FitTier, pickBestModel, rateModelFit } from '../utils/modelFit';
import { Icon } from './Icon';

/**
 * First-run (and Settings) picker for the model that opens automatically when
 * you start a chat. Preselects the best fit for the device and lets the user
 * confirm or choose another.
 */
export function DefaultModelSheet({
  visible,
  onClose,
  onPick,
  currentId,
  allowSkip = false,
}: {
  visible: boolean;
  onClose: () => void;
  onPick: (id: string) => void;
  currentId: string | null;
  /** When true, shows a "Not now" escape (used for the first-run prompt). */
  allowSkip?: boolean;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { models, downloadedIds, deviceProfile } = useApp();

  const ram = deviceProfile?.totalMemoryBytes ?? null;
  const downloaded = models.filter(m => downloadedIds.includes(m.id));
  const best = pickBestModel(downloaded, ram);

  const fitColor: Record<FitTier, string> = {
    great: colors.success,
    good: colors.success,
    slow: colors.warning,
    'too-large': colors.danger,
    unknown: colors.textFaint,
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <Text style={styles.title}>Choose your default model</Text>
          <Text style={styles.subtitle}>
            This one opens automatically when you start a chat. You can change
            it anytime in Settings.
          </Text>

          <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
            {downloaded.map(m => {
              const fit = rateModelFit(m, ram);
              const isCurrent = m.id === currentId;
              const isBest = best?.id === m.id;
              return (
                <Pressable
                  key={m.id}
                  onPress={() => onPick(m.id)}
                  accessibilityRole="button"
                  accessibilityLabel={`Set ${m.name} as default model`}
                  style={({ pressed }) => [
                    styles.row,
                    isCurrent && styles.rowActive,
                    pressed && { opacity: 0.85 },
                  ]}>
                  <View style={{ flex: 1 }}>
                    <View style={styles.nameRow}>
                      <Text style={styles.name} numberOfLines={1}>
                        {m.name}
                      </Text>
                      {isBest && (
                        <View style={styles.bestTag}>
                          <Text style={styles.bestText}>BEST FIT</Text>
                        </View>
                      )}
                    </View>
                    <Text style={styles.meta}>
                      {m.params} • {quantLabel(m.quant)} • {formatBytes(m.sizeBytes)}
                    </Text>
                    {fit.tier !== 'unknown' && (
                      <View style={styles.fitRow}>
                        <View
                          style={[
                            styles.fitDot,
                            { backgroundColor: fitColor[fit.tier] },
                          ]}
                        />
                        <Text style={[styles.fitText, { color: fitColor[fit.tier] }]}>
                          {fit.label}
                        </Text>
                      </View>
                    )}
                  </View>
                  <View
                    style={[styles.radio, isCurrent && styles.radioOn]}>
                    {isCurrent && (
                      <Icon name="check" size={14} color={colors.onPrimary} />
                    )}
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>

          {allowSkip && (
            <Pressable
              style={styles.skip}
              onPress={onClose}
              accessibilityRole="button">
              <Text style={styles.skipText}>Not now</Text>
            </Pressable>
          )}
        </View>
      </View>
    </Modal>
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
      backgroundColor: colors.overlay,
    },
    sheet: {
      backgroundColor: colors.surface,
      borderTopLeftRadius: radius.xl,
      borderTopRightRadius: radius.xl,
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.xxl,
      paddingTop: spacing.sm,
      maxHeight: '82%',
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: colors.border,
      marginBottom: spacing.md,
    },
    title: {
      color: colors.text,
      fontSize: 21,
      fontFamily: fonts.display.bold,
      letterSpacing: -0.3,
    },
    subtitle: {
      color: colors.textDim,
      fontSize: 13.5,
      lineHeight: 19,
      marginTop: spacing.xs,
      marginBottom: spacing.md,
      fontFamily: fonts.body.regular,
    },
    list: { flexGrow: 0 },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      padding: spacing.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      marginBottom: spacing.sm,
      ...shadows.card,
    },
    rowActive: { borderColor: colors.primary, borderWidth: 1.5 },
    nameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    name: {
      color: colors.text,
      fontSize: 15,
      fontFamily: fonts.display.semibold,
      flexShrink: 1,
    },
    bestTag: {
      backgroundColor: colors.surfaceAlt,
      paddingHorizontal: spacing.sm,
      paddingVertical: 3,
      borderRadius: radius.sm,
    },
    bestText: {
      color: colors.primary,
      fontSize: 9.5,
      fontFamily: fonts.body.extrabold,
      letterSpacing: 0.5,
    },
    meta: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 3,
      fontFamily: fonts.body.medium,
    },
    fitRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: 5,
    },
    fitDot: { width: 7, height: 7, borderRadius: 4 },
    fitText: { fontSize: 12, fontFamily: fonts.body.semibold },
    radio: {
      width: 24,
      height: 24,
      borderRadius: 12,
      borderWidth: 2,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
    radioOn: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
    },
    skip: {
      alignSelf: 'center',
      paddingVertical: spacing.md,
      marginTop: spacing.xs,
    },
    skipText: {
      color: colors.textDim,
      fontSize: 14,
      fontFamily: fonts.body.semibold,
    },
  });
