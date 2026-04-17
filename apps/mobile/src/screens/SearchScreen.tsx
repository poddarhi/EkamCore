/**
 * SearchScreen — debounced search with filter chips, infinite scroll,
 * and natural language query detection (S16-005).
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {CardRendererMobile} from '../components/CardRendererMobile';
import {EmptyState} from '../components/ui/EmptyState';
import {FilterChip} from '../components/ui/FilterChip';
import {Skeleton} from '../components/ui/Skeleton';
import {useConnectivity} from '../contexts/ConnectivityContext';
import type {SearchTypeFilter, SearchResponse} from '../types/search';
import type {Card, ResponseEnvelope} from '../types/cards';
import {cachedFetch} from '../api/swrFetcher';
import * as searchApi from '../api/endpoints/search';
import {apiClient} from '../api/ApiClient';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

const FILTERS: {label: string; value: SearchTypeFilter}[] = [
  {label: 'All', value: 'all'},
  {label: 'Events', value: 'calendar'},
  {label: 'Reminders', value: 'reminder'},
  {label: 'Files', value: 'file'},
  {label: 'Photos', value: 'photo'},
  {label: 'People', value: 'contact'},
];

const DEBOUNCE_MS = 300;

function isNaturalLanguageQuery(text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t.startsWith('?') ||
    t.startsWith('what ') ||
    t.startsWith('who ') ||
    t.startsWith('how ') ||
    t.startsWith('when ') ||
    t.startsWith('where ') ||
    t.startsWith('why ')
  );
}

export function SearchScreen() {
  const {isOnline} = useConnectivity();
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<SearchTypeFilter>('all');
  const [results, setResults] = useState<Card[]>([]);
  const [answerText, setAnswerText] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSearch = useCallback(
    async (q: string, filter: SearchTypeFilter) => {
      if (!q.trim()) {
        setResults([]);
        setAnswerText(null);
        setHasSearched(false);
        return;
      }

      setIsLoading(true);
      setHasSearched(true);
      setAnswerText(null);

      try {
        if (isNaturalLanguageQuery(q)) {
          // Natural language → POST /query
          const data = await apiClient.request<ResponseEnvelope>({
            path: '/query',
            method: 'POST',
            body: {query: q.replace(/^\?/, '').trim(), prefer_fast: true},
          });
          setResults(data.cards);
          setAnswerText(data.answer_text);
        } else {
          // Standard search
          const res = await cachedFetch(
            () =>
              searchApi.search({
                q,
                workspace_id: '',
                filters: {type: filter},
              }),
            {cacheType: 'searchResult', cacheId: `${q}:${filter}`},
          );
          setResults(res.data.data);
        }
      } catch {
        // Errors silently clear results — connectivity banner handles UI
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // Debounced search trigger
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query, activeFilter);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, activeFilter, doSearch]);

  const handleFilterPress = useCallback((filter: SearchTypeFilter) => {
    setActiveFilter(filter);
  }, []);

  const renderCard = useCallback(
    ({item}: {item: Card}) => <CardRendererMobile card={item} />,
    [],
  );

  const keyExtractor = useCallback((item: Card) => item.id, []);

  return (
    <View style={styles.root}>
      <ConnectivityBanner />

      {/* Search bar */}
      <View style={styles.searchBar}>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Search everything..."
          placeholderTextColor={Colors.neutral400}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
          accessibilityLabel="Search"
        />
        {query.length > 0 && (
          <TouchableOpacity
            onPress={() => setQuery('')}
            style={styles.clearBtn}
            accessibilityLabel="Clear search">
            <Text style={styles.clearText}>x</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Filter chips */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filterRow}
        contentContainerStyle={styles.filterContent}>
        {FILTERS.map(f => (
          <FilterChip
            key={f.value}
            label={f.label}
            selected={f.value === activeFilter}
            onPress={() => handleFilterPress(f.value)}
          />
        ))}
      </ScrollView>

      {/* Answer text (for NL queries) */}
      {answerText && (
        <View style={styles.answerBox}>
          <Text style={styles.answerText}>{answerText}</Text>
        </View>
      )}

      {/* Results */}
      {isLoading ? (
        <View style={styles.skeletons}>
          <Skeleton height={72} style={{marginHorizontal: sp(4), marginBottom: sp(3)}} />
          <Skeleton height={72} style={{marginHorizontal: sp(4), marginBottom: sp(3)}} />
          <Skeleton height={72} style={{marginHorizontal: sp(4)}} />
        </View>
      ) : (
        <FlatList
          data={results}
          renderItem={renderCard}
          keyExtractor={keyExtractor}
          ListEmptyComponent={
            hasSearched ? (
              <EmptyState
                title={`No results for "${query}"`}
                subtitle="Try different keywords or filters."
              />
            ) : (
              <EmptyState
                title="Search across everything"
                subtitle="Events, reminders, files, photos, and people. Start with ? for natural language queries."
              />
            )
          }
          contentContainerStyle={results.length === 0 ? styles.emptyList : styles.list}
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    marginHorizontal: sp(4),
    marginTop: sp(3),
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.neutral200,
    paddingHorizontal: sp(3),
  },
  input: {
    flex: 1,
    height: 44,
    ...Typography.body,
    color: Colors.neutral900,
  },
  clearBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: Colors.neutral200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  clearText: {...Typography.caption, color: Colors.neutral600},
  filterRow: {maxHeight: 44, marginTop: sp(3)},
  filterContent: {paddingHorizontal: sp(4)},
  answerBox: {
    backgroundColor: Colors.primarySurface,
    marginHorizontal: sp(4),
    marginTop: sp(3),
    padding: sp(4),
    borderRadius: Radius.lg,
  },
  answerText: {...Typography.body, color: Colors.neutral900},
  list: {paddingTop: sp(3), paddingBottom: sp(8)},
  emptyList: {flexGrow: 1},
  skeletons: {paddingTop: sp(4)},
});
