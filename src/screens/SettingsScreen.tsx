import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { BrandLogo } from '../components/BrandLogo';
import { Icon, IconName } from '../components/Icon';
import { ConnectionsSheet } from '../components/ConnectionsSheet';
import { DefaultModelSheet } from '../components/DefaultModelSheet';
import { PersonalizationSheet } from '../components/PersonalizationSheet';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import type { ThemeMode } from '../services/storage';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

const THEME_OPTIONS: { mode: ThemeMode; label: string; icon: IconName }[] = [
  { mode: 'system', label: 'Auto', icon: 'phone' },
  { mode: 'light', label: 'Light', icon: 'sun' },
  { mode: 'dark', label: 'Dark', icon: 'moon' },
];

export function SettingsScreen() {
  const { colors, mode, setMode } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    models,
    loadedModelId,
    downloadedIds,
    memory,
    remoteEndpoints,
    defaultModelId,
    setDefaultModel,
  } = useApp();
  const [showPersonalization, setShowPersonalization] = useState(false);
  const [showConnections, setShowConnections] = useState(false);
  const [showDefaultModel, setShowDefaultModel] = useState(false);

  const loadedModel = models.find(m => m.id === loadedModelId);
  const defaultModel = models.find(m => m.id === defaultModelId);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}>
      {/* Appearance */}
      <Text style={styles.sectionLabel}>APPEARANCE</Text>
      <View style={styles.card}>
        <View style={styles.segmented}>
          {THEME_OPTIONS.map(opt => {
            const selected = mode === opt.mode;
            return (
              <Pressable
                key={opt.mode}
                onPress={() => setMode(opt.mode)}
                accessibilityRole="button"
                accessibilityLabel={`${opt.label} theme`}
                accessibilityState={{ selected }}
                style={[styles.segment, selected && styles.segmentActive]}>
                <Icon
                  name={opt.icon}
                  size={16}
                  color={selected ? colors.onPrimary : colors.textDim}
                />
                <Text
                  style={[
                    styles.segmentText,
                    selected && styles.segmentTextActive,
                  ]}>
                  {opt.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={styles.personalizationHint}>
          Auto follows your phone's light / dark setting.
        </Text>
      </View>

      {/* Default model (on launch) */}
      {downloadedIds.length > 0 && (
        <>
          <Text style={styles.sectionLabel}>ON LAUNCH</Text>
          <Pressable
            style={styles.card}
            onPress={() => setShowDefaultModel(true)}>
            <View style={styles.row}>
              <View style={styles.rowLeft}>
                <Icon name="bolt" size={18} color={colors.primary} />
                <Text style={styles.rowLabel}>Default model</Text>
              </View>
              <View style={styles.rowLeft}>
                <Text style={styles.rowValue} numberOfLines={1}>
                  {defaultModel?.name ??
                    (downloadedIds.length === 1 ? 'Your model' : 'Best fit')}
                </Text>
                <Icon name="chevronRight" size={18} color={colors.textFaint} />
              </View>
            </View>
            <Text style={styles.personalizationHint}>
              Opens automatically in Chat when you start the app.
            </Text>
          </Pressable>
        </>
      )}

      {/* Personalization */}
      <Text style={styles.sectionLabel}>PERSONALIZATION</Text>
      <Pressable style={styles.card} onPress={() => setShowPersonalization(true)}>
        <View style={styles.row}>
          <View style={styles.rowLeft}>
            <Icon name="sparkles" size={18} color={colors.primary} />
            <Text style={styles.rowLabel}>Adapt to me</Text>
          </View>
          <View style={styles.rowLeft}>
            <Text style={styles.rowValue}>{memory.enabled ? 'On' : 'Off'}</Text>
            <Icon name="chevronRight" size={18} color={colors.textFaint} />
          </View>
        </View>
        <Text style={styles.personalizationHint}>
          Learns your preferences from chats to tailor replies — stored only on
          this device.
        </Text>
      </Pressable>

      {/* Connections */}
      <Text style={styles.sectionLabel}>YOUR COMPUTERS</Text>
      <Pressable style={styles.card} onPress={() => setShowConnections(true)}>
        <View style={styles.row}>
          <View style={styles.rowLeft}>
            <Icon name="phone" size={18} color={colors.primary} />
            <Text style={styles.rowLabel}>Remote models</Text>
          </View>
          <View style={styles.rowLeft}>
            <Text style={styles.rowValue}>
              {remoteEndpoints.length > 0
                ? `${remoteEndpoints.length} connected`
                : 'None'}
            </Text>
            <Icon name="chevronRight" size={18} color={colors.textFaint} />
          </View>
        </View>
        <Text style={styles.personalizationHint}>
          Connect to a bigger model on your own computer (Ollama / LM Studio)
          and switch to it inside any chat.
        </Text>
      </Pressable>

      {/* Status */}
      <Text style={styles.sectionLabel}>STATUS</Text>
      <View style={styles.card}>
        <Row
          styles={styles}
          colors={colors}
          icon="bolt"
          label="Loaded model"
          value={loadedModel?.name ?? 'None'}
        />
        <View style={styles.divider} />
        <Row
          styles={styles}
          colors={colors}
          icon="models"
          label="Downloaded models"
          value={`${downloadedIds.length}`}
        />
        <View style={styles.divider} />
        <Row
          styles={styles}
          colors={colors}
          icon="shield"
          label="Runs offline"
          value="Yes"
        />
      </View>

      {/* About */}
      <Text style={styles.sectionLabel}>ABOUT</Text>
      <View style={styles.card}>
        <View style={styles.aboutHeader}>
          <BrandLogo size={48} radius={12} />
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>EkamCore</Text>
            <Text style={styles.cardHint}>Version 1.0.0</Text>
          </View>
        </View>
        <View style={styles.privacyRow}>
          <Icon name="shield" size={18} color={colors.success} />
          <Text style={styles.privacyText}>
            100% on-device. Your conversations never leave your phone.
          </Text>
        </View>
        <Text style={styles.credit}>
          Powered by llama.rn (llama.cpp) on React Native.
        </Text>
      </View>

      <View style={{ height: spacing.xxl }} />

      <PersonalizationSheet
        visible={showPersonalization}
        onClose={() => setShowPersonalization(false)}
      />
      <ConnectionsSheet
        visible={showConnections}
        onClose={() => setShowConnections(false)}
      />
      <DefaultModelSheet
        visible={showDefaultModel}
        currentId={defaultModelId}
        onPick={id => {
          setDefaultModel(id);
          setShowDefaultModel(false);
        }}
        onClose={() => setShowDefaultModel(false)}
      />
    </ScrollView>
  );
}

function Row({
  label,
  value,
  icon,
  styles,
  colors,
}: {
  label: string;
  value: string;
  icon: IconName;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowLeft}>
        <Icon name={icon} size={18} color={colors.textDim} />
        <Text style={styles.rowLabel}>{label}</Text>
      </View>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    content: { padding: spacing.lg },
    sectionLabel: {
      color: colors.textFaint,
      fontSize: 12,
      fontFamily: fonts.display.semibold,
      letterSpacing: 1.5,
      marginBottom: spacing.sm,
      marginTop: spacing.md,
    },
    card: {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      padding: spacing.lg,
      borderWidth: 1,
      borderColor: colors.border,
    },
    cardTitle: { color: colors.text, fontSize: 16, fontFamily: fonts.display.semibold },
    cardHint: {
      color: colors.textDim,
      fontSize: 13,
      marginTop: 2,
      lineHeight: 18,
    },
    row: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: spacing.sm + 2,
    },
    rowLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    rowLabel: { color: colors.textDim, fontSize: 14 },
    rowValue: { color: colors.text, fontSize: 14, fontWeight: '600' },
    personalizationHint: {
      color: colors.textDim,
      fontSize: 12.5,
      lineHeight: 17,
      marginTop: spacing.sm,
    },
    divider: { height: 1, backgroundColor: colors.border },
    segmented: {
      flexDirection: 'row',
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      padding: 3,
      gap: 3,
    },
    segment: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      paddingVertical: spacing.sm + 2,
      borderRadius: radius.md - 3,
    },
    segmentActive: { backgroundColor: colors.primary },
    segmentText: {
      color: colors.textDim,
      fontSize: 13,
      fontFamily: fonts.body.semibold,
    },
    segmentTextActive: { color: colors.onPrimary },
    aboutHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      marginBottom: spacing.md,
    },
    aboutLogo: {
      width: 48,
      height: 48,
      borderRadius: radius.md,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    privacyRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      padding: spacing.md,
      borderRadius: radius.md,
    },
    privacyText: { flex: 1, color: colors.textDim, fontSize: 13, lineHeight: 18 },
    credit: {
      color: colors.textFaint,
      fontSize: 12,
      marginTop: spacing.md,
      lineHeight: 17,
    },
  });
