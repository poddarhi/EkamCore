import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, shadows, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ModelInfo } from '../types';
import { formatBytes, quantLabel } from '../utils/format';
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

  // Brief "ready" celebration the moment a download completes.
  const wasDownloading = useRef(false);
  const [justFinished, setJustFinished] = useState(false);
  const finishAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (wasDownloading.current && !isDownloading && isDownloaded) {
      setJustFinished(true);
      finishAnim.setValue(0);
      Animated.spring(finishAnim, {
        toValue: 1,
        useNativeDriver: true,
        friction: 6,
        tension: 80,
      }).start();
      const t = setTimeout(() => setJustFinished(false), 3200);
      wasDownloading.current = isDownloading;
      return () => clearTimeout(t);
    }
    wasDownloading.current = isDownloading;
  }, [isDownloading, isDownloaded, finishAnim]);

  const pressScale = useRef(new Animated.Value(1)).current;
  const cardPressIn = () =>
    onPress &&
    Animated.spring(pressScale, {
      toValue: 0.985,
      useNativeDriver: true,
      friction: 7,
      tension: 200,
    }).start();
  const cardPressOut = () =>
    Animated.spring(pressScale, {
      toValue: 1,
      useNativeDriver: true,
      friction: 6,
      tension: 160,
    }).start();

  return (
    <Animated.View
      style={[
        styles.card,
        isLoaded && styles.cardActive,
        { transform: [{ scale: pressScale }] },
      ]}>
      <Pressable
        onPress={onPress}
        onPressIn={cardPressIn}
        onPressOut={cardPressOut}
        disabled={!onPress}
        accessibilityRole={onPress ? 'button' : undefined}
        accessibilityLabel={`${model.name}. ${fit.label}`}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{model.name}</Text>
            <Text style={styles.desc}>{model.tagline || model.description}</Text>
          </View>
          {isLoaded ? (
            <View style={styles.loadedBadge}>
              <Icon name="bolt" size={12} color={colors.onPrimary} />
              <Text style={styles.loadedBadgeText}>ACTIVE</Text>
            </View>
          ) : onPress ? (
            <Icon name="chevronRight" size={20} color={colors.textFaint} />
          ) : null}
        </View>

        <View style={styles.metaRow}>
          <Meta label={model.params} styles={styles} />
          <Meta
            label={`${quantLabel(model.quant)} · ${model.quant}`}
            styles={styles}
          />
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
          <View style={styles.progressHeader}>
            <Text style={styles.progressPct}>
              {dl.total > 0 ? `${Math.round(progress * 100)}%` : 'Starting…'}
            </Text>
            <Text style={styles.progressText}>
              {formatBytes(dl.received)}
              {dl.total > 0 ? ` of ${formatBytes(dl.total)}` : ''}
            </Text>
          </View>
          <ProgressBar progress={progress} />
          <Text style={styles.progressHint}>
            Keep the app open while it downloads
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

      {justFinished && !isLoaded && (
        <Animated.View
          style={[
            styles.successBanner,
            {
              opacity: finishAnim,
              transform: [
                {
                  translateY: finishAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [8, 0],
                  }),
                },
              ],
            },
          ]}>
          <Icon name="check" size={15} color={colors.success} />
          <Text style={styles.successText}>Downloaded — ready to load</Text>
        </Animated.View>
      )}

      {!!error && !isDownloading && (
        <View style={styles.errorRow}>
          <Icon name="close" size={14} color={colors.danger} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <View style={styles.actions}>
        {!isDownloaded && !isDownloading && (
          <Button
            label={error ? 'Retry download' : 'Download'}
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
            accessibilityRole="button"
            accessibilityLabel={`Remove ${model.name} from device`}
            hitSlop={8}>
            <Icon name="trash" size={18} color={colors.danger} />
          </Pressable>
        )}
      </View>
    </Animated.View>
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
      ...shadows.card,
    },
    cardActive: { borderColor: colors.primary, borderWidth: 1.5 },
    headerRow: { flexDirection: 'row', alignItems: 'flex-start' },
    name: { color: colors.text, fontSize: 16, fontFamily: fonts.display.semibold },
    desc: {
      color: colors.textDim,
      fontSize: 13,
      marginTop: 2,
      lineHeight: 18,
      fontFamily: fonts.body.regular,
    },
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
    loadedBadgeText: {
      color: colors.onPrimary,
      fontSize: 10,
      fontFamily: fonts.body.extrabold,
      letterSpacing: 0.4,
    },
    metaRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: spacing.sm,
      marginTop: spacing.md,
    },
    metaPill: {
      backgroundColor: colors.surfaceAlt,
      paddingHorizontal: spacing.sm + 2,
      paddingVertical: 4,
      borderRadius: radius.sm,
    },
    metaText: {
      color: colors.textDim,
      fontSize: 12,
      fontFamily: fonts.body.semibold,
    },
    fitRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: spacing.sm,
    },
    fitDot: { width: 8, height: 8, borderRadius: 4 },
    fitText: { fontSize: 12.5, fontFamily: fonts.body.semibold },
    errorRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 6,
      marginTop: spacing.md,
    },
    errorText: {
      flex: 1,
      color: colors.danger,
      fontSize: 12,
      lineHeight: 17,
      fontFamily: fonts.body.medium,
    },
    progressWrap: { marginTop: spacing.md },
    progressHeader: {
      flexDirection: 'row',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      marginBottom: spacing.xs,
    },
    progressPct: {
      color: colors.text,
      fontSize: 15,
      fontFamily: fonts.display.semibold,
    },
    progressText: {
      color: colors.textFaint,
      fontSize: 12,
      marginTop: spacing.xs,
      fontFamily: fonts.body.medium,
    },
    progressHint: {
      color: colors.textFaint,
      fontSize: 11,
      marginTop: spacing.xs,
      fontFamily: fonts.body.regular,
    },
    successBanner: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginTop: spacing.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      borderRadius: radius.md,
      backgroundColor: colors.surfaceAlt,
    },
    successText: {
      color: colors.success,
      fontSize: 13,
      fontFamily: fonts.body.semibold,
    },
    actions: {
      flexDirection: 'row',
      gap: spacing.sm,
      marginTop: spacing.md,
      alignItems: 'center',
    },
    flexBtn: { flex: 1 },
    iconBtn: {
      width: 44,
      height: 44,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
