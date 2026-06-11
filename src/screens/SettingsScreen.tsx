import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { BrandLogo } from '../components/BrandLogo';
import { Icon, IconName } from '../components/Icon';
import { PersonalizationSheet } from '../components/PersonalizationSheet';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

export function SettingsScreen() {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { models, loadedModelId, downloadedIds, memory } = useApp();
  const [showPersonalization, setShowPersonalization] = useState(false);

  const loadedModel = models.find(m => m.id === loadedModelId);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}>
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
