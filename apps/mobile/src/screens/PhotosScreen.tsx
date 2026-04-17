/**
 * PhotosScreen — date-grouped photo grid with thumbnails (S16-005).
 */

import React, {useCallback, useEffect, useState} from 'react';
import {
  Dimensions,
  FlatList,
  Image,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {EmptyState} from '../components/ui/EmptyState';
import {Skeleton} from '../components/ui/Skeleton';
import {cachedFetch} from '../api/swrFetcher';
import * as photosApi from '../api/endpoints/photos';
import {Colors, Typography, sp} from '../design-system/tokens';

const COLUMNS = 3;
const SPACING = 2;
const SCREEN_WIDTH = Dimensions.get('window').width;
const THUMB_SIZE = (SCREEN_WIDTH - SPACING * (COLUMNS + 1)) / COLUMNS;

interface PhotoItem {
  id: string;
  taken_at: string | null;
}

interface DateGroup {
  date: string;
  photos: PhotoItem[];
}

function groupByDate(items: PhotoItem[]): DateGroup[] {
  const groups: Record<string, PhotoItem[]> = {};
  for (const item of items) {
    const date = item.taken_at
      ? new Date(item.taken_at).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        })
      : 'Unknown date';
    if (!groups[date]) groups[date] = [];
    groups[date].push(item);
  }
  return Object.entries(groups).map(([date, photos]) => ({date, photos}));
}

export function PhotosScreen() {
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [cursor, setCursor] = useState<string | undefined>(undefined);

  const fetchPhotos = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await cachedFetch(
        () => photosApi.listPhotos(cursor),
        {cacheType: 'photoList', cacheId: cursor ?? 'first'},
      );
      setPhotos(res.data.items);
    } catch {
      // Connectivity banner handles offline state
    } finally {
      setIsLoading(false);
    }
  }, [cursor]);

  useEffect(() => {
    fetchPhotos();
  }, [fetchPhotos]);

  const groups = groupByDate(photos);

  // Flatten groups into a renderable list: headers + photo rows
  type ListItem = {type: 'header'; date: string} | {type: 'row'; photos: PhotoItem[]};
  const listData: ListItem[] = [];
  for (const g of groups) {
    listData.push({type: 'header', date: g.date});
    // Chunk photos into rows of COLUMNS
    for (let i = 0; i < g.photos.length; i += COLUMNS) {
      listData.push({type: 'row', photos: g.photos.slice(i, i + COLUMNS)});
    }
  }

  const renderItem = useCallback(({item}: {item: ListItem}) => {
    if (item.type === 'header') {
      return (
        <View style={styles.dateHeader}>
          <Text style={styles.dateText}>{item.date}</Text>
        </View>
      );
    }
    return (
      <View style={styles.photoRow}>
        {item.photos.map(photo => (
          <TouchableOpacity
            key={photo.id}
            style={styles.thumbWrap}
            accessibilityLabel="Photo"
            accessibilityRole="image">
            <View style={styles.thumbPlaceholder}>
              <Text style={styles.thumbIcon}>{'[ ]'}</Text>
            </View>
          </TouchableOpacity>
        ))}
        {/* Fill empty slots in last row */}
        {item.photos.length < COLUMNS &&
          Array.from({length: COLUMNS - item.photos.length}).map((_, i) => (
            <View key={`empty-${i}`} style={styles.thumbWrap} />
          ))}
      </View>
    );
  }, []);

  const keyExtractor = useCallback(
    (item: ListItem, index: number) =>
      item.type === 'header' ? `h-${item.date}` : `r-${index}`,
    [],
  );

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />
      <View style={styles.header}>
        <Text style={styles.heading} accessibilityRole="header">
          Photos
        </Text>
      </View>

      {isLoading && photos.length === 0 ? (
        <View style={styles.skeletons}>
          <Skeleton height={20} width={120} style={{marginHorizontal: sp(4), marginBottom: sp(2)}} />
          <View style={styles.photoRow}>
            <Skeleton width={THUMB_SIZE} height={THUMB_SIZE} borderRadius={0} />
            <Skeleton width={THUMB_SIZE} height={THUMB_SIZE} borderRadius={0} />
            <Skeleton width={THUMB_SIZE} height={THUMB_SIZE} borderRadius={0} />
          </View>
        </View>
      ) : (
        <FlatList
          data={listData}
          renderItem={renderItem}
          keyExtractor={keyExtractor}
          ListEmptyComponent={
            <EmptyState title="No photos yet" subtitle="Photos will appear here after ingestion." />
          }
          refreshControl={
            <RefreshControl refreshing={isLoading} onRefresh={fetchPhotos} tintColor={Colors.primary} />
          }
          contentContainerStyle={photos.length === 0 ? styles.emptyList : undefined}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  header: {
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
    paddingBottom: sp(2),
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral200,
  },
  heading: {...Typography.h1, color: Colors.neutral900},
  dateHeader: {
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
    paddingBottom: sp(1),
  },
  dateText: {...Typography.caption, color: Colors.neutral500, fontWeight: '600'},
  photoRow: {
    flexDirection: 'row',
    paddingHorizontal: SPACING,
  },
  thumbWrap: {
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    margin: SPACING / 2,
  },
  thumbPlaceholder: {
    flex: 1,
    backgroundColor: Colors.neutral200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  thumbIcon: {...Typography.caption, color: Colors.neutral400},
  emptyList: {flexGrow: 1},
  skeletons: {paddingTop: sp(4)},
});
