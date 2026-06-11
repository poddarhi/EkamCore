import React, { useMemo } from 'react';
import {
  Linking,
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
import { ModelInfo } from '../types';
import { formatBytes } from '../utils/format';
import { FitTier, rateModelFit } from '../utils/modelFit';
import { Button } from './Button';
import { Icon } from './Icon';
import { ProgressBar } from './ProgressBar';

function huggingFacePage(url: string): string | null {
  const i = url.indexOf('/resolve/');
  if (url.includes('huggingface.co') && i > 0) {
    return url.slice(0, i);
  }
  return null;
}

function formatContext(tokens?: number): string | null {
  if (!tokens) {
    return null;
  }
  return tokens >= 1000 ? `${Math.round(tokens / 1024)}K tokens` : `${tokens} tokens`;
}

function fitHeadline(tier: FitTier, device: string): string {
  switch (tier) {
    case 'great':
      return `Runs great on your ${device}`;
    case 'good':
      return `Runs well on your ${device}`;
    case 'slow':
      return `Might run slowly on your ${device}`;
    case 'too-large':
      return `Likely too large for your ${device}`;
    default:
      return 'Performance depends on your device';
  }
}

export function ModelDetail({
  model,
  onClose,
}: {
  model: ModelInfo | null;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    downloadedIds,
    downloads,
    loadedModelId,
    loadingModelId,
    deviceProfile,
    download,
    cancelDownload,
    removeModel,
    load,
    unload,
  } = useApp();

  if (!model) {
    return null;
  }

  const fit = rateModelFit(model, deviceProfile?.totalMemoryBytes ?? null);
  const fitColor: Record<FitTier, string> = {
    great: colors.success,
    good: colors.success,
    slow: colors.warning,
    'too-large': colors.danger,
    unknown: colors.textFaint,
  };
  const deviceName = deviceProfile?.modelName || 'device';

  const isDownloaded = downloadedIds.includes(model.id);
  const dl = downloads[model.id];
  const isDownloading = !!dl;
  const isLoaded = loadedModelId === model.id;
  const isLoading = loadingModelId === model.id;
  const progress = dl && dl.total > 0 ? dl.received / dl.total : 0;

  const hfPage = huggingFacePage(model.url);
  const ctx = formatContext(model.contextLength);

  const specs: Array<[string, string]> = [
    ['Parameters', model.params],
    ['Quantization', model.quant],
    ['Download size', formatBytes(model.sizeBytes)],
  ];
  if (ctx) {
    specs.push(['Context', ctx]);
  }
  if (model.license) {
    specs.push(['License', model.license]);
  }

  return (
    <Modal
      visible={!!model}
      transparent
      animationType="slide"
      onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={styles.titleRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{model.name}</Text>
                {!!model.publisher && (
                  <Text style={styles.publisher}>by {model.publisher}</Text>
                )}
              </View>
              <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
                <Icon name="close" size={20} color={colors.text} />
              </Pressable>
            </View>

            {!!model.tagline && <Text style={styles.tagline}>{model.tagline}</Text>}

            {deviceProfile?.totalMemoryBytes ? (
              <View style={[styles.fitHero, { borderColor: fitColor[fit.tier] }]}>
                <View style={[styles.fitDot, { backgroundColor: fitColor[fit.tier] }]} />
                <View style={{ flex: 1 }}>
                  <Text style={[styles.fitHeadline, { color: fitColor[fit.tier] }]}>
                    {fitHeadline(fit.tier, deviceName)}
                  </Text>
                  <Text style={styles.fitSub}>
                    {deviceName} • {formatBytes(deviceProfile.totalMemoryBytes)} RAM
                  </Text>
                </View>
              </View>
            ) : null}

            {!!model.goodFor?.length && (
              <View style={styles.chipsRow}>
                {model.goodFor.map(tag => (
                  <View key={tag} style={styles.chip}>
                    <Text style={styles.chipText}>{tag}</Text>
                  </View>
                ))}
              </View>
            )}

            {!!(model.longDescription || model.description) && (
              <Text style={styles.body}>
                {model.longDescription || model.description}
              </Text>
            )}

            <View style={styles.specs}>
              {specs.map(([label, value]) => (
                <View key={label} style={styles.specRow}>
                  <Text style={styles.specLabel}>{label}</Text>
                  <Text style={styles.specValue}>{value}</Text>
                </View>
              ))}
            </View>

            {isDownloading && (
              <View style={styles.progressWrap}>
                <ProgressBar progress={progress} />
                <Text style={styles.progressText}>
                  {formatBytes(dl.received)}
                  {dl.total > 0 ? ` / ${formatBytes(dl.total)}` : ''}
                </Text>
              </View>
            )}

            <View style={styles.actions}>
              {!isDownloaded && !isDownloading && (
                <Button
                  label="Download"
                  icon="download"
                  onPress={() => download(model)}
                  style={{ flex: 1 }}
                />
              )}
              {isDownloading && (
                <Button
                  label="Cancel"
                  variant="danger"
                  onPress={() => cancelDownload(model)}
                  style={{ flex: 1 }}
                />
              )}
              {isDownloaded && !isLoaded && (
                <Button
                  label={isLoading ? 'Loading…' : 'Load'}
                  icon={isLoading ? undefined : 'bolt'}
                  loading={isLoading}
                  onPress={() => load(model)}
                  style={{ flex: 1 }}
                />
              )}
              {isLoaded && (
                <Button
                  label="Unload"
                  variant="secondary"
                  onPress={() => unload()}
                  style={{ flex: 1 }}
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

            {!!hfPage && (
              <Pressable
                style={styles.hfLink}
                onPress={() => Linking.openURL(hfPage)}>
                <Icon name="share" size={15} color={colors.textDim} />
                <Text style={styles.hfLinkText}>View on Hugging Face</Text>
              </Pressable>
            )}
          </ScrollView>
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
      backgroundColor: 'rgba(0,0,0,0.5)',
    },
    sheet: {
      backgroundColor: colors.surface,
      borderTopLeftRadius: radius.lg,
      borderTopRightRadius: radius.lg,
      paddingHorizontal: spacing.xl,
      paddingBottom: spacing.xxl,
      paddingTop: spacing.sm,
      maxHeight: '88%',
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: colors.border,
      marginBottom: spacing.lg,
    },
    titleRow: { flexDirection: 'row', alignItems: 'flex-start' },
    name: { color: colors.text, fontSize: 22, fontFamily: fonts.display.bold },
    publisher: {
      color: colors.textDim,
      fontSize: 13,
      marginTop: 2,
      fontFamily: fonts.body.medium,
    },
    closeBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surfaceAlt,
    },
    tagline: {
      color: colors.textDim,
      fontSize: 14,
      marginTop: spacing.sm,
      lineHeight: 20,
      fontFamily: fonts.body.regular,
    },
    fitHero: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      borderWidth: 1.5,
      borderRadius: radius.md,
      padding: spacing.md,
      marginTop: spacing.lg,
    },
    fitDot: { width: 10, height: 10, borderRadius: 5 },
    fitHeadline: { fontSize: 15, fontFamily: fonts.body.bold },
    fitSub: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    chipsRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: spacing.sm,
      marginTop: spacing.lg,
    },
    chip: {
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.sm,
      paddingHorizontal: spacing.md,
      paddingVertical: 6,
    },
    chipText: {
      color: colors.primary,
      fontSize: 12.5,
      fontFamily: fonts.body.semibold,
    },
    body: {
      color: colors.text,
      fontSize: 14.5,
      lineHeight: 22,
      marginTop: spacing.lg,
      fontFamily: fonts.body.regular,
    },
    specs: {
      marginTop: spacing.lg,
      borderTopWidth: 1,
      borderTopColor: colors.border,
    },
    specRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      paddingVertical: spacing.sm + 2,
      borderBottomWidth: 1,
      borderBottomColor: colors.border,
    },
    specLabel: { color: colors.textDim, fontSize: 13.5, fontFamily: fonts.body.medium },
    specValue: { color: colors.text, fontSize: 13.5, fontFamily: fonts.body.semibold },
    progressWrap: { marginTop: spacing.lg, gap: spacing.xs },
    progressText: { color: colors.textDim, fontSize: 12, fontFamily: fonts.body.regular },
    actions: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      marginTop: spacing.lg,
    },
    iconBtn: {
      width: 46,
      height: 46,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: 'center',
      justifyContent: 'center',
    },
    hfLink: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      marginTop: spacing.lg,
      paddingVertical: spacing.sm,
    },
    hfLinkText: { color: colors.textDim, fontSize: 13.5, fontFamily: fonts.body.semibold },
  });
