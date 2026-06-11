import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Button } from '../components/Button';
import { Icon } from '../components/Icon';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import {
  HfQuant,
  HfRepo,
  listQuants,
  pickRecommended,
  searchGgufModels,
} from '../services/huggingface';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';
import { ModelInfo } from '../types';
import { formatBytes } from '../utils/format';
import { FitTier, rateModelFit } from '../utils/modelFit';

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${n}`;
}

export function HuggingFaceSearch({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { addModel, deviceProfile } = useApp();
  const ram = deviceProfile?.totalMemoryBytes ?? null;

  const [query, setQuery] = useState('');
  const [repos, setRepos] = useState<HfRepo[]>([]);
  const [loading, setLoading] = useState(false);

  const [repo, setRepo] = useState<HfRepo | null>(null);
  const [quants, setQuants] = useState<HfQuant[] | null>(null);
  const [quantsLoading, setQuantsLoading] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // Debounced search whenever the query changes (and on open).
  useEffect(() => {
    if (!visible) {
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      const r = await searchGgufModels(query);
      setRepos(r);
      setLoading(false);
    }, 400);
    return () => clearTimeout(t);
  }, [query, visible]);

  const fitColor: Record<FitTier, string> = {
    great: colors.success,
    good: colors.success,
    slow: colors.warning,
    'too-large': colors.danger,
    unknown: colors.textFaint,
  };

  const openRepo = async (r: HfRepo) => {
    setRepo(r);
    setQuants(null);
    setShowAll(false);
    setQuantsLoading(true);
    setQuants(await listQuants(r.id));
    setQuantsLoading(false);
  };

  const closeRepo = () => {
    setRepo(null);
    setQuants(null);
  };

  const addQuant = (r: HfRepo, q: HfQuant) => {
    const shortName = r.id.split('/').pop() ?? r.id;
    const model: ModelInfo = {
      id: `hf-${r.id}-${q.quant}`.replace(/[^a-zA-Z0-9-]/g, '-').toLowerCase(),
      name: `${shortName} · ${q.quant}`,
      description: `From ${r.id} on Hugging Face.`,
      longDescription: `Added from the Hugging Face repository ${r.id}.`,
      publisher: r.author,
      params: '—',
      quant: q.quant,
      sizeBytes: q.sizeBytes,
      url: q.url,
      custom: true,
    };
    addModel(model);
    closeRepo();
    onClose();
  };

  const recommended = quants ? pickRecommended(quants) : null;
  const others = quants?.filter(q => q !== recommended) ?? [];

  const renderQuant = (q: HfQuant, isRec: boolean) => {
    const fit = rateModelFit({ sizeBytes: q.sizeBytes } as ModelInfo, ram);
    return (
      <View key={q.filename} style={[styles.quantRow, isRec && styles.quantRec]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.quantLabel}>{q.quant}</Text>
          <Text style={styles.quantMeta}>
            {formatBytes(q.sizeBytes)}
            {fit.tier !== 'unknown' ? `  •  ${fit.label}` : ''}
          </Text>
        </View>
        {fit.tier !== 'unknown' && (
          <View style={[styles.dot, { backgroundColor: fitColor[fit.tier] }]} />
        )}
        <Button label="Add" onPress={() => addQuant(repo!, q)} style={styles.addBtn} />
      </View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.root}>
        <View style={styles.header}>
          <Pressable
            onPress={repo ? closeRepo : onClose}
            hitSlop={10}
            style={styles.iconBtn}>
            <Icon name="arrowLeft" size={22} color={colors.text} />
          </Pressable>
          <Text style={styles.title} numberOfLines={1}>
            {repo ? repo.id.split('/').pop() : 'Browse Hugging Face'}
          </Text>
        </View>

        {!repo ? (
          <>
            <View style={styles.searchWrap}>
              <TextInput
                style={styles.search}
                placeholder="Search models (e.g. gemma, qwen, phi)…"
                placeholderTextColor={colors.textFaint}
                value={query}
                onChangeText={setQuery}
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            {loading ? (
              <ActivityIndicator
                color={colors.primary}
                style={{ marginTop: spacing.xl }}
              />
            ) : (
              <FlatList
                data={repos}
                keyExtractor={r => r.id}
                contentContainerStyle={styles.list}
                keyboardShouldPersistTaps="handled"
                ListEmptyComponent={
                  <Text style={styles.empty}>
                    No GGUF models found. Check your connection or try another
                    search.
                  </Text>
                }
                renderItem={({ item }) => (
                  <Pressable style={styles.repoRow} onPress={() => openRepo(item)}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.repoName} numberOfLines={1}>
                        {item.id.split('/').pop()}
                      </Text>
                      <Text style={styles.repoMeta} numberOfLines={1}>
                        {item.author} • ↓ {compact(item.downloads)} • ♥{' '}
                        {compact(item.likes)}
                      </Text>
                    </View>
                    <Icon name="chevronRight" size={20} color={colors.textFaint} />
                  </Pressable>
                )}
              />
            )}
          </>
        ) : (
          <ScrollView contentContainerStyle={styles.list}>
            <Text style={styles.repoFull}>{repo.id}</Text>
            {quantsLoading ? (
              <ActivityIndicator
                color={colors.primary}
                style={{ marginTop: spacing.xl }}
              />
            ) : !quants || quants.length === 0 ? (
              <Text style={styles.empty}>
                No single-file GGUF quantizations found in this repo.
              </Text>
            ) : (
              <>
                <Text style={styles.sectionLabel}>Recommended</Text>
                {recommended && renderQuant(recommended, true)}
                {others.length > 0 && (
                  <Pressable
                    style={styles.moreBtn}
                    onPress={() => setShowAll(v => !v)}>
                    <Text style={styles.moreText}>
                      {showAll
                        ? 'Hide other quantizations'
                        : `More quantizations (${others.length})`}
                    </Text>
                    <Icon
                      name="chevronRight"
                      size={16}
                      color={colors.primary}
                    />
                  </Pressable>
                )}
                {showAll && others.map(q => renderQuant(q, false))}
              </>
            )}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg, paddingTop: 56 },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.sm,
    },
    iconBtn: {
      width: 38,
      height: 38,
      borderRadius: 19,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: colors.surfaceAlt,
    },
    title: { color: colors.text, fontSize: 20, fontFamily: fonts.display.bold, flex: 1 },
    searchWrap: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
    search: {
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.md,
      color: colors.text,
      fontSize: 15,
      fontFamily: fonts.body.regular,
    },
    list: { padding: spacing.lg, paddingTop: spacing.sm },
    empty: {
      color: colors.textDim,
      fontSize: 14,
      textAlign: 'center',
      marginTop: spacing.xl,
      lineHeight: 20,
      paddingHorizontal: spacing.lg,
    },
    repoRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      marginBottom: spacing.sm,
    },
    repoName: { color: colors.text, fontSize: 15, fontFamily: fonts.body.semibold },
    repoMeta: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    repoFull: {
      color: colors.textDim,
      fontSize: 13,
      marginBottom: spacing.lg,
      fontFamily: fonts.body.medium,
    },
    sectionLabel: {
      color: colors.textDim,
      fontSize: 12.5,
      fontFamily: fonts.body.bold,
      textTransform: 'uppercase',
      letterSpacing: 0.6,
      marginBottom: spacing.sm,
    },
    quantRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      marginBottom: spacing.sm,
    },
    quantRec: { borderColor: colors.primary, borderWidth: 1.5 },
    quantLabel: { color: colors.text, fontSize: 15, fontFamily: fonts.body.bold },
    quantMeta: {
      color: colors.textDim,
      fontSize: 12.5,
      marginTop: 2,
      fontFamily: fonts.body.regular,
    },
    dot: { width: 9, height: 9, borderRadius: 4.5 },
    addBtn: { paddingHorizontal: spacing.lg },
    moreBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 4,
      paddingVertical: spacing.md,
    },
    moreText: { color: colors.primary, fontSize: 14, fontFamily: fonts.body.semibold },
  });
