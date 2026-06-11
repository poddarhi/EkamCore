import React, { useMemo, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { listRemoteModels, RemoteEndpoint } from '../services/remote';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { Button } from './Button';
import { Icon } from './Icon';

const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export function ConnectionsSheet({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { remoteEndpoints, addEndpoint, removeEndpoint } = useApp();

  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [kind, setKind] = useState<RemoteEndpoint['kind']>('ollama');
  const [testing, setTesting] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const reset = () => {
    setName('');
    setBaseUrl('');
    setApiKey('');
    setKind('ollama');
    setNote(null);
  };

  const onAdd = async () => {
    const url = baseUrl.trim();
    if (!url) {
      setNote('Enter the server URL.');
      return;
    }
    const ep: RemoteEndpoint = {
      id: uid(),
      name: name.trim() || (kind === 'ollama' ? 'My Ollama' : 'My server'),
      baseUrl: url,
      kind,
      apiKey: apiKey.trim() || undefined,
    };
    setTesting(true);
    setNote(null);
    const models = await listRemoteModels(ep);
    setTesting(false);
    addEndpoint(ep);
    setNote(
      models.length > 0
        ? `Connected — found ${models.length} model${models.length === 1 ? '' : 's'}.`
        : 'Saved, but no models responded. You can still select it later once it’s reachable.',
    );
    setName('');
    setBaseUrl('');
    setApiKey('');
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
            <View style={styles.titleRow}>
              <Text style={styles.title}>Your computers</Text>
              <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
                <Icon name="close" size={20} color={colors.text} />
              </Pressable>
            </View>
            <Text style={styles.intro}>
              Connect to a bigger model running on a computer you own (Ollama or
              an OpenAI-compatible server like LM Studio), over your home network
              or a private mesh like Tailscale. Then pick it in any chat with the
              “+” button.
            </Text>

            {remoteEndpoints.length > 0 && (
              <>
                <Text style={styles.sectionLabel}>Connected</Text>
                {remoteEndpoints.map(ep => (
                  <View key={ep.id} style={styles.epRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.epName}>{ep.name}</Text>
                      <Text style={styles.epMeta} numberOfLines={1}>
                        {ep.kind} • {ep.baseUrl}
                      </Text>
                    </View>
                    <Pressable onPress={() => removeEndpoint(ep.id)} hitSlop={8}>
                      <Icon name="trash" size={17} color={colors.textFaint} />
                    </Pressable>
                  </View>
                ))}
              </>
            )}

            <Text style={styles.sectionLabel}>Add a connection</Text>
            <View style={styles.kindRow}>
              {(['ollama', 'openai'] as const).map(k => (
                <Pressable
                  key={k}
                  style={[styles.kindChip, kind === k && styles.kindChipActive]}
                  onPress={() => setKind(k)}>
                  <Text
                    style={[
                      styles.kindText,
                      kind === k && styles.kindTextActive,
                    ]}>
                    {k === 'ollama' ? 'Ollama' : 'OpenAI-compatible'}
                  </Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              style={styles.input}
              placeholder="Name (e.g. Home Mac)"
              placeholderTextColor={colors.textFaint}
              value={name}
              onChangeText={setName}
            />
            <TextInput
              style={styles.input}
              placeholder={
                kind === 'ollama'
                  ? 'http://100.x.x.x:11434'
                  : 'http://100.x.x.x:1234/v1'
              }
              placeholderTextColor={colors.textFaint}
              value={baseUrl}
              onChangeText={setBaseUrl}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TextInput
              style={styles.input}
              placeholder="API key (optional)"
              placeholderTextColor={colors.textFaint}
              value={apiKey}
              onChangeText={setApiKey}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />
            <Button
              label={testing ? 'Connecting…' : 'Add connection'}
              loading={testing}
              onPress={onAdd}
              style={{ marginTop: spacing.sm }}
            />
            {!!note && <Text style={styles.note}>{note}</Text>}
            {remoteEndpoints.length > 0 && (
              <Pressable onPress={reset} style={{ alignSelf: 'center', marginTop: spacing.md }}>
                <Text style={styles.clearForm}>Clear form</Text>
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
      maxHeight: '90%',
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: colors.border,
      marginBottom: spacing.lg,
    },
    titleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    title: { color: colors.text, fontSize: 22, fontFamily: fonts.display.bold },
    closeBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surfaceAlt,
    },
    intro: {
      color: colors.textDim,
      fontSize: 13.5,
      lineHeight: 20,
      marginTop: spacing.sm,
      fontFamily: fonts.body.regular,
    },
    sectionLabel: {
      color: colors.textDim,
      fontSize: 12.5,
      fontFamily: fonts.body.bold,
      textTransform: 'uppercase',
      letterSpacing: 0.6,
      marginTop: spacing.xl,
      marginBottom: spacing.sm,
    },
    epRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      padding: spacing.md,
      marginBottom: spacing.sm,
    },
    epName: { color: colors.text, fontSize: 15, fontFamily: fonts.body.semibold },
    epMeta: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    kindRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
    kindChip: {
      flex: 1,
      alignItems: 'center',
      paddingVertical: spacing.sm + 2,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.bg,
    },
    kindChipActive: { borderColor: colors.primary, backgroundColor: colors.surfaceAlt },
    kindText: { color: colors.textDim, fontSize: 13.5, fontFamily: fonts.body.semibold },
    kindTextActive: { color: colors.primary },
    input: {
      backgroundColor: colors.bg,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
      color: colors.text,
      fontSize: 15,
      marginBottom: spacing.md,
      fontFamily: fonts.body.regular,
    },
    note: {
      color: colors.textDim,
      fontSize: 13,
      textAlign: 'center',
      marginTop: spacing.md,
      lineHeight: 18,
      fontFamily: fonts.body.regular,
    },
    clearForm: { color: colors.primary, fontSize: 13.5, fontFamily: fonts.body.semibold },
  });
