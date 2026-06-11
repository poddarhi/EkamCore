import React, { useEffect, useMemo, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { Button } from './Button';
import { Icon } from './Icon';

export function PersonalizationSheet({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const {
    memory,
    loadedModelId,
    messages,
    setMemoryEnabled,
    updateMemory,
    learnFromChats,
    clearMemory,
  } = useApp();

  const [style, setStyle] = useState(memory.style);
  const [newFact, setNewFact] = useState('');
  const [learning, setLearning] = useState(false);
  const [learnNote, setLearnNote] = useState<string | null>(null);

  // Re-sync local style when the sheet opens or memory changes externally.
  useEffect(() => {
    if (visible) {
      setStyle(memory.style);
      setLearnNote(null);
    }
  }, [visible, memory.style]);

  const addFact = () => {
    const f = newFact.trim();
    if (!f) {
      return;
    }
    updateMemory([...memory.facts, f], memory.style);
    setNewFact('');
  };

  const removeFact = (i: number) => {
    updateMemory(
      memory.facts.filter((_, idx) => idx !== i),
      memory.style,
    );
  };

  const onLearn = async () => {
    setLearning(true);
    setLearnNote(null);
    const ok = await learnFromChats();
    setLearning(false);
    setLearnNote(
      ok
        ? 'Updated from this conversation.'
        : 'Nothing new to learn yet — chat a bit more first.',
    );
  };

  const canLearn = !!loadedModelId && messages.length > 0 && !learning;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={styles.titleRow}>
              <Text style={styles.title}>Personalization</Text>
              <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
                <Icon name="close" size={20} color={colors.text} />
              </Pressable>
            </View>

            <View style={styles.toggleRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.toggleLabel}>Adapt to me</Text>
                <Text style={styles.toggleSub}>
                  Uses what it’s learned to tailor replies. Stored only on this
                  device — turn off any time.
                </Text>
              </View>
              <Switch
                value={memory.enabled}
                onValueChange={setMemoryEnabled}
                trackColor={{ false: colors.border, true: colors.primary }}
                thumbColor={colors.surface}
              />
            </View>

            <Text style={styles.sectionLabel}>What it knows about you</Text>
            {memory.facts.length === 0 ? (
              <Text style={styles.empty}>
                Nothing yet. Add facts below, or learn from a chat.
              </Text>
            ) : (
              memory.facts.map((f, i) => (
                <View key={`${f}-${i}`} style={styles.factRow}>
                  <Text style={styles.factText}>{f}</Text>
                  <Pressable onPress={() => removeFact(i)} hitSlop={8}>
                    <Icon name="trash" size={16} color={colors.textFaint} />
                  </Pressable>
                </View>
              ))
            )}
            <View style={styles.addRow}>
              <TextInput
                style={styles.addInput}
                placeholder="Add a fact (e.g. I'm a nurse)"
                placeholderTextColor={colors.textFaint}
                value={newFact}
                onChangeText={setNewFact}
                onSubmitEditing={addFact}
                returnKeyType="done"
              />
              <Pressable onPress={addFact} style={styles.addBtn}>
                <Icon name="plus" size={18} color={colors.onPrimary} />
              </Pressable>
            </View>

            <Text style={styles.sectionLabel}>Preferred answer style</Text>
            <TextInput
              style={styles.styleInput}
              placeholder="e.g. Short, direct, with bullet points"
              placeholderTextColor={colors.textFaint}
              value={style}
              onChangeText={setStyle}
              onBlur={() => updateMemory(memory.facts, style)}
              multiline
            />

            <Button
              label={learning ? 'Learning…' : 'Learn from this chat'}
              icon={learning ? undefined : 'sparkles'}
              loading={learning}
              onPress={onLearn}
              disabled={!canLearn}
              style={styles.learnBtn}
            />
            {!loadedModelId && (
              <Text style={styles.hint}>Load a model to learn from chats.</Text>
            )}
            {!!learnNote && <Text style={styles.hint}>{learnNote}</Text>}

            <Pressable onPress={clearMemory} style={styles.clearBtn}>
              <Text style={styles.clearText}>Clear everything it knows</Text>
            </Pressable>
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
    toggleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      marginTop: spacing.lg,
    },
    toggleLabel: { color: colors.text, fontSize: 16, fontFamily: fonts.body.bold },
    toggleSub: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      lineHeight: 17,
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
    empty: {
      color: colors.textFaint,
      fontSize: 13.5,
      fontFamily: fonts.body.regular,
    },
    factRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      paddingVertical: spacing.sm + 2,
      paddingHorizontal: spacing.md,
      marginBottom: spacing.sm,
    },
    factText: { flex: 1, color: colors.text, fontSize: 14, fontFamily: fonts.body.regular },
    addRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.xs },
    addInput: {
      flex: 1,
      backgroundColor: colors.bg,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      color: colors.text,
      fontSize: 14,
      fontFamily: fonts.body.regular,
    },
    addBtn: {
      width: 42,
      height: 42,
      borderRadius: radius.md,
      backgroundColor: colors.primary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    styleInput: {
      backgroundColor: colors.bg,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
      color: colors.text,
      fontSize: 14,
      minHeight: 60,
      textAlignVertical: 'top',
      fontFamily: fonts.body.regular,
    },
    learnBtn: { marginTop: spacing.xl },
    hint: {
      color: colors.textDim,
      fontSize: 12.5,
      textAlign: 'center',
      marginTop: spacing.sm,
      fontFamily: fonts.body.regular,
    },
    clearBtn: { alignSelf: 'center', marginTop: spacing.lg, padding: spacing.sm },
    clearText: { color: colors.danger, fontSize: 13.5, fontFamily: fonts.body.semibold },
  });
