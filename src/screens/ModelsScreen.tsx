import React, { useMemo, useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { ModelCard } from '../components/ModelCard';
import { ModelDetail } from '../components/ModelDetail';
import { HuggingFaceSearch } from './HuggingFaceSearch';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ModelInfo } from '../types';
import { formatBytes } from '../utils/format';
import { fitOrder, rateModelFit, tierHeading } from '../utils/modelFit';

export function ModelsScreen() {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { models, addCustomModel, deviceProfile } = useApp();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [detailModel, setDetailModel] = useState<ModelInfo | null>(null);
  const [showBrowse, setShowBrowse] = useState(false);

  const ram = deviceProfile?.totalMemoryBytes ?? null;
  const featured = models.filter(m => !m.custom);
  const custom = models.filter(m => m.custom);

  // Best-fitting first; within a tier, larger (more capable) first.
  const sortedFeatured = [...featured].sort((a, b) => {
    const d =
      fitOrder(rateModelFit(a, ram).tier) - fitOrder(rateModelFit(b, ram).tier);
    return d !== 0 ? d : b.sizeBytes - a.sizeBytes;
  });

  // Walk the sorted list, inserting a tier header whenever the tier changes
  // (only when we actually know the device's RAM).
  const featuredNodes: React.ReactNode[] = [];
  let lastTier: string | null = null;
  for (const m of sortedFeatured) {
    const tier = rateModelFit(m, ram).tier;
    if (ram && tier !== lastTier) {
      featuredNodes.push(
        <Text key={`hdr-${tier}`} style={styles.sectionHeader}>
          {tierHeading(tier)}
        </Text>,
      );
      lastTier = tier;
    }
    featuredNodes.push(
      <ModelCard key={m.id} model={m} onPress={() => setDetailModel(m)} />,
    );
  }

  const onAdd = async () => {
    if (!url.trim()) {
      return;
    }
    await addCustomModel(name, url);
    setName('');
    setUrl('');
    setShowAdd(false);
  };

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <Text style={styles.intro}>
          Download a model once, then run it fully offline. Everything stays on
          your device.
        </Text>
        {deviceProfile?.totalMemoryBytes ? (
          <View style={styles.deviceBanner}>
            <Icon name="phone" size={18} color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.deviceTitle}>
                {deviceProfile.modelName || 'Your device'}
              </Text>
              <Text style={styles.deviceMeta}>
                {formatBytes(deviceProfile.totalMemoryBytes)} RAM • estimates
                below are tailored to it
              </Text>
            </View>
          </View>
        ) : null}
        {featuredNodes}
        {custom.length > 0 && (
          <>
            <Text style={styles.sectionHeader}>Your added models</Text>
            {custom.map(m => (
              <ModelCard
                key={m.id}
                model={m}
                onPress={() => setDetailModel(m)}
              />
            ))}
          </>
        )}
        <Button
          label="Browse Hugging Face"
          icon="sparkles"
          onPress={() => setShowBrowse(true)}
          style={styles.addBtn}
        />
        <Button
          label="Add from GGUF URL"
          icon="plus"
          variant="secondary"
          onPress={() => setShowAdd(true)}
          style={styles.addBtn}
        />
        <View style={{ height: spacing.xxl }} />
      </ScrollView>

      <ModelDetail model={detailModel} onClose={() => setDetailModel(null)} />

      <HuggingFaceSearch
        visible={showBrowse}
        onClose={() => setShowBrowse(false)}
      />

      <Modal
        visible={showAdd}
        animationType="slide"
        transparent
        onRequestClose={() => setShowAdd(false)}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={[styles.modalRoot, { backgroundColor: colors.overlay }]}>
          <View style={styles.sheet}>
            <View style={styles.handle} />
            <Text style={styles.sheetTitle}>Add a custom model</Text>
            <Text style={styles.sheetHint}>
              Paste a direct link to a .gguf file (e.g. a Hugging Face
              “resolve” URL).
            </Text>
            <TextInput
              placeholder="Display name (optional)"
              placeholderTextColor={colors.textFaint}
              value={name}
              onChangeText={setName}
              style={styles.input}
            />
            <TextInput
              placeholder="https://…/model.gguf"
              placeholderTextColor={colors.textFaint}
              value={url}
              onChangeText={setUrl}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.input}
            />
            <View style={styles.sheetActions}>
              <Button
                label="Cancel"
                variant="ghost"
                onPress={() => setShowAdd(false)}
                style={{ flex: 1 }}
              />
              <Button label="Add" onPress={onAdd} style={{ flex: 1 }} />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    list: { padding: spacing.lg },
    intro: {
      color: colors.textDim,
      fontSize: 13,
      lineHeight: 19,
      marginBottom: spacing.lg,
    },
    deviceBanner: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      padding: spacing.md,
      marginBottom: spacing.lg,
    },
    deviceTitle: {
      color: colors.text,
      fontSize: 14,
      fontFamily: fonts.body.bold,
    },
    deviceMeta: {
      color: colors.textDim,
      fontSize: 12,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    sectionHeader: {
      color: colors.textDim,
      fontSize: 12.5,
      fontFamily: fonts.body.bold,
      textTransform: 'uppercase',
      letterSpacing: 0.6,
      marginTop: spacing.sm,
      marginBottom: spacing.sm,
    },
    addBtn: { marginTop: spacing.sm },
    modalRoot: { flex: 1, justifyContent: 'flex-end' },
    sheet: {
      backgroundColor: colors.surface,
      borderTopLeftRadius: radius.lg,
      borderTopRightRadius: radius.lg,
      padding: spacing.xl,
      paddingBottom: spacing.xxl,
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: colors.border,
      marginBottom: spacing.lg,
    },
    sheetTitle: { color: colors.text, fontSize: 19, fontFamily: fonts.display.semibold },
    sheetHint: {
      color: colors.textDim,
      fontSize: 13,
      marginTop: spacing.xs,
      marginBottom: spacing.lg,
      lineHeight: 18,
    },
    input: {
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
      color: colors.text,
      fontSize: 15,
      marginBottom: spacing.md,
      borderWidth: 1,
      borderColor: colors.border,
    },
    sheetActions: {
      flexDirection: 'row',
      gap: spacing.md,
      marginTop: spacing.sm,
    },
  });
