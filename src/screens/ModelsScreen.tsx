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
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { formatBytes } from '../utils/format';

export function ModelsScreen() {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { models, addCustomModel, deviceProfile } = useApp();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');

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
        {models.map(m => (
          <ModelCard key={m.id} model={m} />
        ))}
        <Button
          label="Add model from GGUF URL"
          icon="plus"
          variant="secondary"
          onPress={() => setShowAdd(true)}
          style={styles.addBtn}
        />
        <View style={{ height: spacing.xxl }} />
      </ScrollView>

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
