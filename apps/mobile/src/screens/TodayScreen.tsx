/**
 * TodayScreen — card list with connectivity-aware rendering (S16-004).
 *
 * Behavior per connectivity state:
 *   CONNECTED:            live data, fresh cards, no banner
 *   DEGRADED:             cards + yellow "Slow connection" banner
 *   RECONNECTING:         cached cards + spinner "Reconnecting..."
 *   DISCONNECTED_CACHED:  cached cards + orange "Showing cached data"
 *   DISCONNECTED_EMPTY:   full-screen "Hub unreachable" with retry
 *   HUB_SLEEPING:         "Your hub appears to be sleeping" with wake guidance
 */

import React, {useCallback} from 'react';
import {FlatList, RefreshControl, SafeAreaView, StyleSheet, Text, View} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {CardRendererMobile} from '../components/CardRendererMobile';
import {EmptyState} from '../components/ui/EmptyState';
import {Skeleton} from '../components/ui/Skeleton';
import {useConnectivity} from '../contexts/ConnectivityContext';
import {useTodayQuery} from '../hooks/useTodayQuery';
import type {Card} from '../types/cards';
import {Colors, Typography, sp} from '../design-system/tokens';

export function TodayScreen() {
  const {state: connState} = useConnectivity();
  const {data, isLoading, isStale, error, refresh} = useTodayQuery();

  const cards = data?.cards ?? [];

  const renderCard = useCallback(
    ({item}: {item: Card}) => <CardRendererMobile card={item} />,
    [],
  );

  const keyExtractor = useCallback((item: Card) => item.id, []);

  // Full-screen offline states
  if (!isLoading && !data && connState === 'DISCONNECTED_EMPTY') {
    return (
      <SafeAreaView style={styles.root}>
        <ConnectivityBanner />
        <EmptyState
          title="Hub unreachable"
          subtitle="Cannot connect to your EkamCore hub and no cached data is available."
          actionLabel="Retry"
          onAction={refresh}
        />
      </SafeAreaView>
    );
  }

  if (!isLoading && !data && connState === 'HUB_SLEEPING') {
    return (
      <SafeAreaView style={styles.root}>
        <ConnectivityBanner />
        <EmptyState
          title="Hub is sleeping"
          subtitle="Your Mac appears to be asleep. Wake it up or wait for it to come online."
          actionLabel="Retry"
          onAction={refresh}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />

      {isStale && data && (
        <View style={styles.staleBanner}>
          <Text style={styles.staleText}>Showing cached data</Text>
        </View>
      )}

      {isLoading && cards.length === 0 ? (
        <View style={styles.skeletonContainer}>
          <Skeleton height={24} width={200} style={{marginBottom: sp(4), marginHorizontal: sp(4)}} />
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
                title="Could not load today"
                subtitle={error.message}
                actionLabel="Retry"
                onAction={refresh}
              />
            ) : (
              <EmptyState title="No items today" subtitle="Your schedule is clear." />
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
  list: {paddingTop: sp(3), paddingBottom: sp(8)},
  emptyList: {flexGrow: 1},
  skeletonContainer: {paddingTop: sp(6)},
  staleBanner: {
    backgroundColor: Colors.warningSurface,
    paddingVertical: 4,
    alignItems: 'center',
  },
  staleText: {...Typography.caption, color: Colors.warning},
});
