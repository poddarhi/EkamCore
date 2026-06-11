import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { GradientFill } from '../components/GradientFill';
import { Icon } from '../components/Icon';
import { useApp } from '../context/AppContext';
import { useTheme } from '../context/ThemeContext';
import {
  CATEGORY_ORDER,
  TOOLS,
  Tool,
  ToolCategory,
  toolsByCategory,
} from '../data/tools';
import { radius, spacing, type ThemeColors } from '../theme';
import { fonts } from '../typography';

type Filter = 'All' | ToolCategory;

export function ToolsListScreen({
  onOpen,
  onGoToModels,
}: {
  onOpen: (id: string) => void;
  onGoToModels: () => void;
}) {
  const { colors } = useTheme();
  const styles = useMemo(() => makeStyles(colors), [colors]);
  const { downloadedIds } = useApp();
  const hasModel = downloadedIds.length > 0;
  const [filter, setFilter] = useState<Filter>('All');

  const filters: Filter[] = ['All', ...CATEGORY_ORDER];
  const groups =
    filter === 'All'
      ? toolsByCategory()
      : toolsByCategory().filter(g => g.category === filter);

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.intro}>
          {TOOLS.length} focused assistants that run entirely on your device.
          Pick one, fill in a few details, and get a polished result in seconds.
        </Text>

        {!hasModel && (
          <Pressable style={styles.notice} onPress={onGoToModels}>
            <View style={styles.noticeIcon}>
              <Icon name="download" size={16} color={colors.primary} />
            </View>
            <Text style={styles.noticeText}>
              Download a model first to power these tools.
            </Text>
            <Icon name="chevronRight" size={16} color={colors.textDim} />
          </Pressable>
        )}

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filterRow}>
          {filters.map(f => {
            const active = filter === f;
            return (
              <Pressable
                key={f}
                onPress={() => setFilter(f)}
                style={[styles.filterChip, active && styles.filterChipActive]}>
                <Text
                  style={[
                    styles.filterText,
                    { color: active ? colors.onPrimary : colors.textDim },
                  ]}>
                  {f}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {groups.map(group => (
          <View key={group.category} style={styles.section}>
            {filter === 'All' && (
              <Text style={styles.sectionLabel}>{group.category}</Text>
            )}
            {group.tools.map((tool, i) => (
              <ToolCard
                key={tool.id}
                tool={tool}
                index={i}
                colors={colors}
                styles={styles}
                onPress={() => onOpen(tool.id)}
              />
            ))}
          </View>
        ))}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </View>
  );
}

function ToolCard({
  tool,
  index,
  colors,
  styles,
  onPress,
}: {
  tool: Tool;
  index: number;
  colors: ThemeColors;
  styles: ReturnType<typeof makeStyles>;
  onPress: () => void;
}) {
  const enter = useRef(new Animated.Value(0)).current;
  const press = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(enter, {
      toValue: 1,
      duration: 360,
      delay: index * 70,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [enter, index]);

  const scale = Animated.multiply(
    enter.interpolate({ inputRange: [0, 1], outputRange: [0.97, 1] }),
    press.interpolate({ inputRange: [0, 1], outputRange: [1, 0.97] }),
  );

  return (
    <Animated.View
      style={{
        opacity: enter,
        transform: [
          { translateY: enter.interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) },
          { scale },
        ],
      }}>
      <Pressable
        onPress={onPress}
        onPressIn={() =>
          Animated.timing(press, {
            toValue: 1,
            duration: 90,
            useNativeDriver: true,
          }).start()
        }
        onPressOut={() =>
          Animated.timing(press, {
            toValue: 0,
            duration: 140,
            useNativeDriver: true,
          }).start()
        }
        style={[styles.card, { shadowColor: tool.accent[0] }]}>
        <View style={[styles.iconTile, { backgroundColor: tool.accent[0] }]}>
          <GradientFill colors={tool.accent} radius={16} />
          <Icon name={tool.icon} size={24} color="#FFFFFF" />
        </View>
        <View style={styles.cardBody}>
          <Text style={styles.cardTitle}>{tool.title}</Text>
          <Text style={styles.cardDesc} numberOfLines={2}>
            {tool.description}
          </Text>
        </View>
        <Icon name="chevronRight" size={18} color={colors.textFaint} />
      </Pressable>
    </Animated.View>
  );
}

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.bg },
    content: { padding: spacing.lg },
    intro: {
      color: colors.textDim,
      fontSize: 14,
      lineHeight: 20,
      marginBottom: spacing.lg,
    },
    notice: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      padding: spacing.md,
      marginBottom: spacing.lg,
    },
    noticeIcon: {
      width: 30,
      height: 30,
      borderRadius: 15,
      backgroundColor: colors.surface,
      alignItems: 'center',
      justifyContent: 'center',
    },
    noticeText: {
      flex: 1,
      color: colors.text,
      fontSize: 13,
      fontFamily: fonts.body.medium,
    },
    filterRow: { gap: spacing.sm, paddingBottom: spacing.lg, paddingRight: spacing.lg },
    filterChip: {
      paddingHorizontal: spacing.md + 2,
      paddingVertical: spacing.sm,
      borderRadius: radius.pill,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
    },
    filterChipActive: {
      backgroundColor: colors.primary,
      borderColor: colors.primary,
    },
    filterText: { fontSize: 13, fontFamily: fonts.body.semibold },
    section: { marginBottom: spacing.sm },
    sectionLabel: {
      color: colors.textFaint,
      fontSize: 12,
      fontFamily: fonts.display.semibold,
      letterSpacing: 1.4,
      textTransform: 'uppercase',
      marginBottom: spacing.sm,
      marginTop: spacing.xs,
    },
    card: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.md,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      marginBottom: spacing.md,
      shadowOpacity: 0.18,
      shadowRadius: 12,
      shadowOffset: { width: 0, height: 6 },
      elevation: 2,
    },
    iconTile: {
      width: 52,
      height: 52,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
    },
    cardBody: { flex: 1, gap: 3 },
    cardTitle: {
      color: colors.text,
      fontSize: 16,
      fontFamily: fonts.display.semibold,
    },
    cardDesc: { color: colors.textDim, fontSize: 13, lineHeight: 18 },
  });
