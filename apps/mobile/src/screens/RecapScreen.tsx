/**
 * RecapScreen — daily/weekly recap with period toggle and date navigation (S16-004).
 */

import React, {useCallback, useState} from 'react';
import {
  FlatList,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {CardRendererMobile} from '../components/CardRendererMobile';
import {EmptyState} from '../components/ui/EmptyState';
import {Skeleton} from '../components/ui/Skeleton';
import {useRecapQuery} from '../hooks/useRecapQuery';
import type {RecapPeriod} from '../types/api';
import type {Card} from '../types/cards';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

function addDays(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function todayISO(): string {
  return new Date().toISOString().split('T')[0];
}

export function RecapScreen() {
  const [period, setPeriod] = useState<RecapPeriod>('daily');
  const [date, setDate] = useState(todayISO());
  const {data, isLoading, isStale, error, refresh} = useRecapQuery(period, date);

  const cards = data?.cards ?? [];
  const step = period === 'weekly' ? 7 : 1;

  const goPrev = useCallback(() => setDate(d => addDays(d, -step)), [step]);
  const goNext = useCallback(() => setDate(d => addDays(d, step)), [step]);

  const renderCard = useCallback(
    ({item}: {item: Card}) => <CardRendererMobile card={item} />,
    [],
  );
  const keyExtractor = useCallback((item: Card) => item.id, []);

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />

      {/* Period toggle */}
      <View style={styles.header}>
        <View style={styles.toggleRow}>
          <TouchableOpacity
            style={[styles.toggleBtn, period === 'daily' && styles.toggleActive]}
            onPress={() => setPeriod('daily')}
            accessibilityRole="tab"
            accessibilityState={{selected: period === 'daily'}}
            accessibilityLabel="Daily recap">
            <Text style={[styles.toggleText, period === 'daily' && styles.toggleTextActive]}>
              Daily
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.toggleBtn, period === 'weekly' && styles.toggleActive]}
            onPress={() => setPeriod('weekly')}
            accessibilityRole="tab"
            accessibilityState={{selected: period === 'weekly'}}
            accessibilityLabel="Weekly recap">
            <Text style={[styles.toggleText, period === 'weekly' && styles.toggleTextActive]}>
              Weekly
            </Text>
          </TouchableOpacity>
        </View>

        {/* Date navigation */}
        <View style={styles.dateRow}>
          <TouchableOpacity
            onPress={goPrev}
            style={styles.dateArrow}
            accessibilityLabel="Previous period">
            <Text style={styles.arrowText}>{'<'}</Text>
          </TouchableOpacity>
          <Text style={styles.dateLabel} accessibilityRole="text">
            {formatDate(date)}
          </Text>
          <TouchableOpacity
            onPress={goNext}
            style={styles.dateArrow}
            accessibilityLabel="Next period">
            <Text style={styles.arrowText}>{'>'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {isStale && data && (
        <View style={styles.staleBanner}>
          <Text style={styles.staleText}>Showing cached data</Text>
        </View>
      )}

      {isLoading && cards.length === 0 ? (
        <View style={styles.skeletons}>
          <Skeleton height={80} style={{marginBottom: sp(3), marginHorizontal: sp(4)}} />
          <Skeleton height={80} style={{marginBottom: sp(3), marginHorizontal: sp(4)}} />
          <Skeleton height={80} style={{marginHorizontal: sp(4)}} />
        </View>
      ) : (
        <FlatList
          data={cards}
          renderItem={renderCard}
          keyExtractor={keyExtractor}
          ListEmptyComponent={
            error ? (
              <EmptyState
                title="Could not load recap"
                subtitle={error.message}
                actionLabel="Retry"
                onAction={refresh}
              />
            ) : (
              <EmptyState
                title="No recap data"
                subtitle={`Nothing to recap for ${formatDate(date)}.`}
              />
            )
          }
          refreshControl={
            <RefreshControl refreshing={isLoading} onRefresh={refresh} tintColor={Colors.primary} />
          }
          contentContainerStyle={cards.length === 0 ? styles.emptyList : styles.list}
          showsVerticalScrollIndicator={false}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  header: {
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral200,
    paddingBottom: sp(3),
  },
  toggleRow: {
    flexDirection: 'row',
    marginHorizontal: sp(4),
    marginTop: sp(3),
    backgroundColor: Colors.neutral100,
    borderRadius: Radius.md,
    padding: 2,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: sp(2),
    alignItems: 'center',
    borderRadius: Radius.md - 2,
  },
  toggleActive: {backgroundColor: Colors.white},
  toggleText: {...Typography.small, color: Colors.neutral500, fontWeight: '500'},
  toggleTextActive: {color: Colors.primary, fontWeight: '600'},
  dateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: sp(3),
    paddingHorizontal: sp(4),
  },
  dateArrow: {
    width: 44,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  arrowText: {...Typography.h2, color: Colors.primary},
  dateLabel: {...Typography.body, color: Colors.neutral900, fontWeight: '600'},
  list: {paddingTop: sp(3), paddingBottom: sp(8)},
  emptyList: {flexGrow: 1},
  skeletons: {paddingTop: sp(4)},
  staleBanner: {
    backgroundColor: Colors.warningSurface,
    paddingVertical: 4,
    alignItems: 'center',
  },
  staleText: {...Typography.caption, color: Colors.warning},
});
