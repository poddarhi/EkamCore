import Clipboard from '@react-native-clipboard/clipboard';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import Markdown from 'react-native-markdown-display';
import { GradientFill } from '../components/GradientFill';
import { Icon } from '../components/Icon';
import { TypingDots } from '../components/TypingDots';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import { getTool } from '../data/tools';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

export function ToolRunnerScreen({
  toolId,
  keyboardHeight = 0,
  onGoToModels,
}: {
  toolId: string;
  keyboardHeight?: number;
  onGoToModels: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const mdStyles = useMemo(() => makeMarkdownStyles(colors), [colors]);
  const {
    models,
    downloadedIds,
    loadedModelId,
    loadingModelId,
    load,
    complete,
    stop,
    isGenerating,
  } = useApp();

  const tool = getTool(toolId);

  const [values, setValues] = useState<Record<string, string>>({});
  const [opts, setOpts] = useState<Record<string, string>>({});
  const [output, setOutput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!tool) {
      return;
    }
    setValues({});
    setOpts(
      tool.options.reduce(
        (acc, g) => ({ ...acc, [g.key]: g.choices[0].value }),
        {} as Record<string, string>,
      ),
    );
    setOutput('');
    setError(null);
  }, [tool]);

  const downloadedModels = useMemo(
    () => models.filter(m => downloadedIds.includes(m.id)),
    [models, downloadedIds],
  );

  if (!tool) {
    return null;
  }
  const accent = tool.accent;

  const applyExample = (ex: { values: Record<string, string>; opts?: Record<string, string> }) => {
    setValues(v => ({ ...v, ...ex.values }));
    if (ex.opts) {
      setOpts(o => ({ ...o, ...ex.opts }));
    }
    setError(null);
  };

  const onGenerate = async () => {
    const missing = tool.fields.find(f => f.required && !values[f.key]?.trim());
    if (missing) {
      setError(`Please fill in: ${missing.label}`);
      return;
    }
    if (!loadedModelId) {
      setError('Select a model below to use this tool.');
      return;
    }
    setError(null);
    setOutput('');
    setCopied(false);
    const { system, prompt } = tool.build(values, opts);
    try {
      await complete({
        system,
        prompt,
        temperature: tool.temperature,
        maxTokens: tool.maxTokens,
        onUpdate: setOutput,
      });
    } catch (e: any) {
      setError(e?.message ?? 'Generation failed.');
    }
  };

  const onShare = () => {
    if (output) {
      Share.share({ message: output }).catch(() => {});
    }
  };

  const onCopy = () => {
    if (!output) {
      return;
    }
    Clipboard.setString(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const showOutput = output.length > 0 || isGenerating;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.content,
        { paddingBottom: keyboardHeight + spacing.xxl },
      ]}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}>
      {/* Hero */}
      <View style={[styles.hero, { backgroundColor: accent[0] }]}>
        <GradientFill colors={accent} radius={radius.lg} />
        <View style={styles.heroTopRow}>
          <View style={styles.heroIcon}>
            <Icon name={tool.icon} size={24} color="#FFFFFF" />
          </View>
          <View style={styles.heroPill}>
            <Icon name="shield" size={11} color="#FFFFFF" />
            <Text style={styles.heroPillText}>On-device</Text>
          </View>
        </View>
        <Text style={styles.heroTitle}>{tool.title}</Text>
        <Text style={styles.heroDesc}>{tool.description}</Text>
      </View>

      {/* Examples */}
      {tool.examples && tool.examples.length > 0 && (
        <View style={styles.exampleBlock}>
          <View style={styles.exampleHeader}>
            <Icon name="sparkles" size={14} color={accent[0]} />
            <Text style={styles.exampleLabel}>Try an example</Text>
          </View>
          <View style={styles.chips}>
            {tool.examples.map(ex => (
              <Pressable
                key={ex.label}
                onPress={() => applyExample(ex)}
                style={[styles.exampleChip, { borderColor: accent[0] }]}>
                <Text style={[styles.exampleChipText, { color: accent[0] }]}>
                  {ex.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      {/* Inputs */}
      {tool.fields.map(f => (
        <View key={f.key} style={styles.field}>
          <Text style={styles.label}>
            {f.label}
            {f.required && <Text style={styles.req}> *</Text>}
          </Text>
          {f.hint && <Text style={styles.hint}>{f.hint}</Text>}
          <TextInput
            style={[
              styles.input,
              f.multiline && styles.inputMultiline,
              focused === f.key && { borderColor: accent[0], borderWidth: 1.5 },
            ]}
            placeholder={f.placeholder}
            placeholderTextColor={colors.textFaint}
            value={values[f.key] ?? ''}
            onChangeText={t => setValues(v => ({ ...v, [f.key]: t }))}
            onFocus={() => setFocused(f.key)}
            onBlur={() => setFocused(null)}
            multiline={f.multiline}
          />
        </View>
      ))}

      {/* Options */}
      {tool.options.map(group => (
        <View key={group.key} style={styles.field}>
          <Text style={styles.optionLabel}>{group.label}</Text>
          <View style={styles.chips}>
            {group.choices.map(choice => (
              <SelectChip
                key={choice.value}
                label={choice.label}
                active={opts[group.key] === choice.value}
                accent={accent}
                styles={styles}
                colors={colors}
                onPress={() =>
                  setOpts(o => ({ ...o, [group.key]: choice.value }))
                }
              />
            ))}
          </View>
        </View>
      ))}

      {/* Model picker */}
      <View style={styles.field}>
        <Text style={styles.optionLabel}>Model</Text>
        {downloadedModels.length === 0 ? (
          <Pressable style={styles.notice} onPress={onGoToModels}>
            <Icon name="download" size={16} color={colors.primary} />
            <Text style={styles.noticeText}>Download a model to continue</Text>
            <Icon name="chevronRight" size={15} color={colors.textDim} />
          </Pressable>
        ) : (
          <View style={styles.chips}>
            {downloadedModels.map(m => {
              const active = loadedModelId === m.id;
              const busy = loadingModelId === m.id;
              return (
                <SelectChip
                  key={m.id}
                  label={m.name}
                  active={active}
                  accent={accent}
                  styles={styles}
                  colors={colors}
                  onPress={() => !active && !busy && load(m)}
                  leading={
                    busy ? (
                      <ActivityIndicator
                        size="small"
                        color={active ? '#FFFFFF' : accent[0]}
                      />
                    ) : active ? (
                      <Icon name="check" size={14} color="#FFFFFF" />
                    ) : undefined
                  }
                />
              );
            })}
          </View>
        )}
      </View>

      {error && (
        <View style={styles.errorBox}>
          <Icon name="close" size={15} color={colors.danger} />
          <Text style={styles.error}>{error}</Text>
        </View>
      )}

      {/* Generate / Stop */}
      {isGenerating ? (
        <Pressable style={[styles.cta, styles.ctaStop]} onPress={stop}>
          <Icon name="stop" size={18} color={colors.onPrimary} />
          <Text style={styles.ctaText}>Stop generating</Text>
        </Pressable>
      ) : (
        <Pressable
          style={({ pressed }) => [
            styles.cta,
            { shadowColor: accent[0], backgroundColor: accent[0] },
            pressed && styles.ctaPressed,
          ]}
          onPress={onGenerate}>
          <GradientFill colors={accent} radius={radius.md} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} />
          <Icon name="bolt" size={18} color="#FFFFFF" />
          <Text style={styles.ctaText}>{tool.cta}</Text>
        </Pressable>
      )}

      {/* Output */}
      {showOutput && (
        <View
          style={[
            styles.outputCard,
            isGenerating && { borderColor: accent[0] },
          ]}>
          <View style={styles.outputHeader}>
            <View style={styles.outputHeaderLeft}>
              <Text style={styles.outputLabel}>RESULT</Text>
              {isGenerating && (
                <View style={[styles.liveDot, { backgroundColor: accent[0] }]} />
              )}
            </View>
            {!isGenerating && output.length > 0 && (
              <View style={styles.outputActions}>
                <ActionBtn
                  styles={styles}
                  colors={colors}
                  icon={copied ? 'check' : 'copy'}
                  label={copied ? 'Copied' : 'Copy'}
                  active={copied}
                  accent={accent[0]}
                  onPress={onCopy}
                />
                <ActionBtn
                  styles={styles}
                  colors={colors}
                  icon="share"
                  label="Share"
                  onPress={onShare}
                />
                <ActionBtn
                  styles={styles}
                  colors={colors}
                  icon="refresh"
                  label="Redo"
                  onPress={onGenerate}
                />
              </View>
            )}
          </View>

          {isGenerating && output.length === 0 ? (
            <View style={styles.thinking}>
              <TypingDots color={accent[0]} />
              <Text style={styles.thinkingText}>Generating…</Text>
            </View>
          ) : isGenerating ? (
            <Text style={styles.streamText}>
              {output}
              <Text style={{ color: accent[0] }}>▍</Text>
            </Text>
          ) : (
            <Markdown style={mdStyles}>{output}</Markdown>
          )}
        </View>
      )}
    </ScrollView>
  );
}

function SelectChip({
  label,
  active,
  accent,
  onPress,
  leading,
  styles,
  colors,
}: {
  label: string;
  active: boolean;
  accent: [string, string];
  onPress: () => void;
  leading?: React.ReactNode;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  const press = useRef(new Animated.Value(0)).current;
  const animate = (to: number) =>
    Animated.spring(press, {
      toValue: to,
      useNativeDriver: true,
      friction: 7,
      tension: 200,
    }).start();
  const scale = press.interpolate({ inputRange: [0, 1], outputRange: [1, 0.94] });

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        onPress={onPress}
        onPressIn={() => animate(1)}
        onPressOut={() => animate(0)}
        style={[
          styles.chip,
          active && { backgroundColor: accent[0], shadowColor: accent[0] },
          active && styles.chipActive,
        ]}>
        {active && <GradientFill colors={accent} radius={radius.pill} />}
        {leading}
        <Text
          style={[
            styles.chipText,
            active ? styles.chipTextActive : { color: colors.textDim },
          ]}>
          {label}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

function ActionBtn({
  icon,
  label,
  onPress,
  active,
  accent,
  styles,
  colors,
}: {
  icon: 'copy' | 'share' | 'refresh' | 'check';
  label: string;
  onPress: () => void;
  active?: boolean;
  accent?: string;
  styles: ReturnType<typeof makeStyles>;
  colors: ThemeColors;
}) {
  const tint = active && accent ? accent : colors.textDim;
  return (
    <Pressable onPress={onPress} hitSlop={6} style={styles.actionBtn}>
      <Icon name={icon} size={15} color={tint} />
      <Text style={[styles.actionText, { color: tint }]}>{label}</Text>
    </Pressable>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    content: { padding: spacing.lg },

    hero: {
      borderRadius: radius.lg,
      padding: spacing.lg,
      marginBottom: spacing.lg,
      overflow: 'hidden',
      shadowColor: '#000',
      shadowOpacity: 0.2,
      shadowRadius: 16,
      shadowOffset: { width: 0, height: 8 },
      elevation: 4,
    },
    heroTopRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: spacing.md,
    },
    heroIcon: {
      width: 46,
      height: 46,
      borderRadius: 14,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'rgba(255,255,255,0.22)',
    },
    heroPill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 5,
      backgroundColor: 'rgba(255,255,255,0.2)',
      borderRadius: radius.pill,
      paddingHorizontal: spacing.sm + 2,
      paddingVertical: 5,
    },
    heroPillText: {
      color: '#FFFFFF',
      fontSize: 11,
      fontFamily: fonts.body.semibold,
      letterSpacing: 0.3,
    },
    heroTitle: {
      color: '#FFFFFF',
      fontSize: 22,
      fontFamily: fonts.display.bold,
      letterSpacing: -0.3,
    },
    heroDesc: {
      color: 'rgba(255,255,255,0.92)',
      fontSize: 13.5,
      lineHeight: 20,
      marginTop: 5,
      fontFamily: fonts.body.regular,
    },

    exampleBlock: { marginBottom: spacing.lg },
    exampleHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: spacing.sm,
    },
    exampleLabel: {
      color: colors.textDim,
      fontSize: 13,
      fontFamily: fonts.body.semibold,
    },
    exampleChip: {
      borderWidth: 1,
      borderRadius: radius.pill,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      backgroundColor: colors.surface,
    },
    exampleChipText: { fontSize: 13, fontFamily: fonts.body.semibold },

    field: { marginBottom: spacing.lg },
    label: {
      color: colors.text,
      fontSize: 14,
      fontFamily: fonts.body.semibold,
      marginBottom: spacing.xs,
    },
    hint: {
      color: colors.textFaint,
      fontSize: 12,
      lineHeight: 16,
      marginBottom: spacing.sm,
    },
    req: { color: colors.danger },
    input: {
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
      color: colors.text,
      fontSize: 15,
      marginTop: spacing.xs,
    },
    inputMultiline: { minHeight: 110, textAlignVertical: 'top' },
    optionLabel: {
      color: colors.textFaint,
      fontSize: 12,
      fontFamily: fonts.display.semibold,
      letterSpacing: 1.2,
      textTransform: 'uppercase',
      marginBottom: spacing.sm + 2,
    },
    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    chip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.pill,
      paddingHorizontal: spacing.md + 2,
      paddingVertical: spacing.sm + 3,
      minHeight: 42,
    },
    chipActive: {
      shadowOpacity: 0.38,
      shadowRadius: 9,
      shadowOffset: { width: 0, height: 4 },
      elevation: 3,
    },
    chipText: { color: colors.textDim, fontSize: 13.5, fontFamily: fonts.body.semibold },
    chipTextActive: { color: '#FFFFFF' },
    notice: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      padding: spacing.md,
    },
    noticeText: { flex: 1, color: colors.text, fontSize: 13, fontFamily: fonts.body.medium },

    errorBox: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm + 2,
      marginBottom: spacing.md,
    },
    error: { flex: 1, color: colors.danger, fontSize: 13, fontFamily: fonts.body.medium },

    cta: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      borderRadius: radius.md,
      paddingVertical: spacing.md + 4,
      overflow: 'hidden',
      shadowOpacity: 0.4,
      shadowRadius: 14,
      shadowOffset: { width: 0, height: 6 },
      elevation: 4,
    },
    ctaPressed: { transform: [{ scale: 0.985 }], opacity: 0.95 },
    ctaStop: { backgroundColor: colors.danger },
    ctaText: { color: '#FFFFFF', fontSize: 16, fontFamily: fonts.body.bold },

    outputCard: {
      marginTop: spacing.xl,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.lg,
      padding: spacing.lg,
    },
    outputHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: spacing.sm,
    },
    outputHeaderLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    outputLabel: {
      color: colors.textFaint,
      fontSize: 12,
      fontFamily: fonts.display.semibold,
      letterSpacing: 1.4,
    },
    liveDot: { width: 8, height: 8, borderRadius: 4 },
    outputActions: { flexDirection: 'row', gap: spacing.xs },
    actionBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 5,
      paddingHorizontal: spacing.sm + 2,
      paddingVertical: 6,
      borderRadius: radius.sm,
      backgroundColor: colors.surfaceAlt,
    },
    actionText: { fontSize: 12, fontFamily: fonts.body.semibold },
    streamText: {
      color: colors.text,
      fontSize: 15,
      lineHeight: 22,
      fontFamily: fonts.body.regular,
    },
    thinking: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    thinkingText: { color: colors.textDim, fontSize: 14, fontFamily: fonts.body.medium },
  });

const makeMarkdownStyles = (colors: ThemeColors) =>
  ({
    body: {
      color: colors.text,
      fontSize: 15,
      lineHeight: 22,
      fontFamily: fonts.body.regular,
    },
    heading1: { color: colors.text, fontSize: 20, fontFamily: fonts.display.bold },
    heading2: { color: colors.text, fontSize: 18, fontFamily: fonts.display.semibold },
    heading3: { color: colors.text, fontSize: 16, fontFamily: fonts.display.semibold },
    strong: { fontFamily: fonts.body.bold, color: colors.text },
    bullet_list: { marginVertical: 4 },
    ordered_list: { marginVertical: 4 },
    code_inline: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: fonts.mono,
      borderRadius: 4,
      paddingHorizontal: 4,
    },
    fence: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: fonts.mono,
      borderRadius: 8,
      padding: spacing.md,
    },
    code_block: {
      backgroundColor: colors.surfaceAlt,
      color: colors.text,
      fontFamily: fonts.mono,
      borderRadius: 8,
      padding: spacing.md,
    },
    link: { color: colors.primary },
  } as any);
