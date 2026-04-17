/**
 * PeopleScreen — searchable list of confirmed persons (S16-006).
 */

import React, {useCallback, useRef, useState} from 'react';
import {
  FlatList,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {EmptyState} from '../components/ui/EmptyState';
import {Skeleton} from '../components/ui/Skeleton';
import {usePeopleList} from '../hooks/usePeopleList';
import type {Person} from '../api/endpoints/people';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

interface Props {
  onPersonPress?: (person: Person) => void;
  onReviewPress?: () => void;
}

export function PeopleScreen({onPersonPress, onReviewPress}: Props) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback((text: string) => {
    setSearch(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(text), 300);
  }, []);

  const {people, isLoading, error, refresh, loadMore} =
    usePeopleList(debouncedSearch || undefined);

  const renderPerson = useCallback(
    ({item}: {item: Person}) => (
      <TouchableOpacity
        style={styles.personRow}
        onPress={() => onPersonPress?.(item)}
        accessibilityLabel={`${item.display_name}`}
        accessibilityRole="button">
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {item.display_name.charAt(0).toUpperCase()}
          </Text>
        </View>
        <View style={styles.personInfo}>
          <Text style={styles.personName} numberOfLines={1}>
            {item.display_name}
          </Text>
          <Text style={styles.personMeta}>
            {item.trust_source === 'face_cluster' ? 'Face cluster' : 'Contact'}
            {item.face_count != null && ` \u2022 ${item.face_count} faces`}
            {item.confirmed_at && ' \u2022 Confirmed'}
          </Text>
        </View>
      </TouchableOpacity>
    ),
    [onPersonPress],
  );

  const keyExtractor = useCallback((item: Person) => item.id, []);

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerRow}>
          <Text style={styles.heading} accessibilityRole="header">
            People
          </Text>
          {onReviewPress && (
            <TouchableOpacity
              style={styles.reviewBtn}
              onPress={onReviewPress}
              accessibilityLabel="Review queue"
              accessibilityRole="button">
              <Text style={styles.reviewBtnText}>Review</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Search bar */}
        <View style={styles.searchBar}>
          <TextInput
            style={styles.searchInput}
            value={search}
            onChangeText={handleSearchChange}
            placeholder="Search people..."
            placeholderTextColor={Colors.neutral400}
            autoCapitalize="none"
            autoCorrect={false}
            accessibilityLabel="Search people"
          />
          {search.length > 0 && (
            <TouchableOpacity
              onPress={() => {
                setSearch('');
                setDebouncedSearch('');
              }}
              style={styles.clearBtn}
              accessibilityLabel="Clear search">
              <Text style={styles.clearText}>x</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* List */}
      {isLoading && people.length === 0 ? (
        <View style={styles.skeletons}>
          {Array.from({length: 5}).map((_, i) => (
            <View key={i} style={styles.skeletonRow}>
              <Skeleton width={44} height={44} borderRadius={22} />
              <View style={{flex: 1, marginLeft: sp(3)}}>
                <Skeleton height={16} width={150} style={{marginBottom: 4}} />
                <Skeleton height={12} width={100} />
              </View>
            </View>
          ))}
        </View>
      ) : (
        <FlatList
          data={people}
          renderItem={renderPerson}
          keyExtractor={keyExtractor}
          onEndReached={loadMore}
          onEndReachedThreshold={0.3}
          ListEmptyComponent={
            error ? (
              <EmptyState
                title="Could not load people"
                subtitle={error.message}
                actionLabel="Retry"
                onAction={refresh}
              />
            ) : debouncedSearch ? (
              <EmptyState
                title={`No results for "${debouncedSearch}"`}
                subtitle="Try a different name."
              />
            ) : (
              <EmptyState
                title="No people yet"
                subtitle="People appear here after face clustering identifies them in your photos."
              />
            )
          }
          refreshControl={
            <RefreshControl
              refreshing={isLoading}
              onRefresh={refresh}
              tintColor={Colors.primary}
            />
          }
          contentContainerStyle={
            people.length === 0 ? styles.emptyList : styles.list
          }
          ItemSeparatorComponent={() => <View style={styles.separator} />}
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
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
  },
  heading: {...Typography.h1, color: Colors.neutral900},
  reviewBtn: {
    paddingHorizontal: sp(3),
    paddingVertical: sp(1),
    backgroundColor: Colors.primarySurface,
    borderRadius: Radius.full,
  },
  reviewBtnText: {...Typography.caption, color: Colors.primary, fontWeight: '600'},
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: sp(4),
    marginTop: sp(3),
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.neutral200,
    backgroundColor: Colors.neutral50,
    paddingHorizontal: sp(3),
  },
  searchInput: {
    flex: 1,
    height: 40,
    ...Typography.body,
    color: Colors.neutral900,
  },
  clearBtn: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: Colors.neutral200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  clearText: {...Typography.caption, color: Colors.neutral600},
  list: {paddingBottom: sp(8)},
  emptyList: {flexGrow: 1},
  personRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: sp(4),
    paddingVertical: sp(3),
    backgroundColor: Colors.white,
    minHeight: 60,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.primarySurface,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: sp(3),
  },
  avatarText: {...Typography.h3, color: Colors.primary},
  personInfo: {flex: 1},
  personName: {...Typography.body, color: Colors.neutral900, fontWeight: '500'},
  personMeta: {...Typography.caption, color: Colors.neutral500, marginTop: 2},
  separator: {
    height: 1,
    backgroundColor: Colors.neutral100,
    marginLeft: sp(4) + 44 + sp(3),
  },
  skeletons: {paddingTop: sp(3)},
  skeletonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: sp(4),
    paddingVertical: sp(3),
  },
});
