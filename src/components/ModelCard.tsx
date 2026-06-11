import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ModelInfo } from '../types';
import { formatBytes } from '../utils/format';
import { FitTier, rateModelFit } from '../utils/modelFit';
import { Button } from './Button';
import { Icon } from './Icon';
import { ProgressBar } from './ProgressBar';

export function ModelCard({
  model,
  onPress,
}: {
  model: ModelInfo;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    downloadedIds,
    downloads,
    downloadErrors,
    loadedModelId,
    loadingModelId,
    loadProgress,
    deviceProfile,
    download,
    cancelDownload,
    removeModel,
    load,
    unload,
  } = useApp();

  const fit = rateModelFit(model, deviceProfile?.totalMemoryBytes ?? null);
  const fitColor: Record<FitTier, string> = {
    great: colors.success,
    good: colors.success,
    slow: colors.warning,
    'too-large': colors.danger,
    unknown: colors.textFaint,
  };

  const isDownloaded = downloadedIds.includes(model.id);
  const dl = downloads[model.id];
  const error = downloadErrors[model.id];
  const isDownloading = !!dl;
  const isLoaded = loadedModelId === model.id;
  const isLoading = loadingModelId === model.id;

  const progress = dl && dl.total > 0 ? dl.received / dl.total : 0;

  return (
    <View style={[styles.card, isLoaded && styles.cardActive]}>
      <Pressable onPress={onPress} disabled={!onPress}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{model.name}</Text>
            <Text style={styles.desc}>{model.tagline || model.description}</Text>
          </View>
          {isLoaded ? (
            <View style={styles.loadedBadge}>
              <Icon name="bolt" size={12} color={colors.onPrimary} />
              <Text style={styles.loadedBadgeText}>LOADED</Text>
            </View>
          ) : onPress ? (
            <Icon name="chevronRight" size={20} color={colors.textFaint} />
          ) : null}
        </View>

        <View style={styles.metaRow}>
          <Meta label={model.params} styles={styles} />
          <Meta label={model.quant} styles={styles} />
          <Meta label={formatBytes(model.sizeBytes)} styles={styles} />
        </View>

        {fit.tier !== 'unknown' && (
          <View style={styles.fitRow}>
            <View style={[styles.fitDot, { backgroundColor: fitColor[fit.tier] }]} />
            <Text style={[styles.fitText, { color: fitColor[fit.tier] }]}>
              {fit.label}
            </Text>
          </View>
        )}
      </Pressable>

      {isDownloading && (
        <View style={styles.progressWrap}>
          <ProgressBar progress={progress} />
          <Text style={styles.progressText}>
            {formatBytes(dl.received)}
            {dl.total > 0 ? ` / ${formatBytes(dl.total)}` : ''}
            {dl.total > 0 ? `  •  ${Math.round(progress * 100)}%` : ''}
          </Text>
        </View>
      )}

      {isLoading && (
        <View style={styles.progressWrap}>
          <ProgressBar progress={loadProgress / 100} />
          <Text style={styles.progressText}>
            Loading into memory… {Math.round(loadProgress)}%
          </Text>
        </View>
      )}

      {!!error && !isDownloading && (
        <Text style={styles.errorText}>{error}</Text>
      )}

      <View style={styles.actions}>
        {!isDownloaded && !isDownloading && (
          <Button
            label={error ? 'Retry' : 'Download'}
            icon="download"
            onPress={() => download(model)}
            style={styles.flexBtn}
          />
        )}
        {isDownloading && (
          <Button
            label="Cancel"
            variant="danger"
            onPress={() => cancelDownload(model)}
            style={styles.flexBtn}
          />
        )}
        {isDownloaded && !isLoaded && (
          <Button
            label={isLoading ? 'Loading…' : 'Load'}
            icon={isLoading ? undefined : 'bolt'}
            loading={isLoading}
            onPress={() => load(model)}
            style={styles.flexBtn}
          />
        )}
        {isLoaded && (
          <Button
            label="Unload"
            variant="secondary"
            onPress={() => unload()}
            style={styles.flexBtn}
          />
        )}
        {isDownloaded && !isDownloading && (
          <Pressable
            onPress={() => removeModel(model)}
            style={styles.iconBtn}
            hitSlop={8}>
            <Icon name="trash" size={18} color={colors.danger} />
          </Pressable>
        )}
      </View>
    </View>
  );
}

function Meta({
  label,
  styles,
}: {
  label: string;
  styles: ReturnType<typeof makeStyles>;
}) {
  return (
    <View style={styles.metaPill}>
      <Text style={styles.metaText}>{label}</Text>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    card: {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      padding: spacing.lg,
      marginBottom: spacing.md,
      borderWidth: 1,
      borderColor: colors.border,
    },
    cardActive: { borderColor: colors.primary, borderWidth: 1.5 },
    headerRow: { flexDirection: 'row', alignItems: 'flex-start' },
    name: { color: colors.text, fontSize: 16, fontFamily: fonts.display.semibold },
    desc: { color: colors.textDim, fontSize: 13, marginTop: 2, lineHeight: 18 },
    loadedBadge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      backgroundColor: colors.primary,
      paddingHorizontal: spacing.sm,
      paddingVertical: 4,
      borderRadius: radius.sm,
      marginLeft: spacing.sm,
    },
    loadedBadgeText: { color: colors.onPrimary, fontSize: 10, fontWeight: '800' },
    metaRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
    metaPill: {
      backgroundColor: colors.surfaceAlt,
      paddingHorizontal: spacing.sm + 2,
      paddingVertical: 4,
      borderRadius: radius.sm,
    },
    metaText: { color: colors.textDim, fontSize: 12, fontWeight: '600' },
    fitRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: spacing.sm,
    },
    fitDot: { width: 8, height: 8, borderRadius: 4 },
    fitText: { fontSize: 12.5, fontFamily: fonts.body.semibold },
    errorText: {
      color: colors.danger,
      fontSize: 12,
      marginTop: spacing.md,
      lineHeight: 17,
    },
    progressWrap: { marginTop: spacing.md },
    progressText: { color: colors.textFaint, fontSize: 12, marginTop: spacing.xs },
    actions: {
      flexDirection: 'row',
      gap: spacing.sm,
      marginTop: spacing.md,
      alignItems: 'center',
    },
    flexBtn: { flex: 1 },
    iconBtn: {
      width: 42,
      height: 42,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
