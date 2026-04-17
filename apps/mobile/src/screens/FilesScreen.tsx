/**
 * FilesScreen — list view with file type icons and metadata (S16-005).
 */

import React, {useCallback, useEffect, useState} from 'react';
import {
  FlatList,
  Linking,
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
import {apiClient} from '../api/ApiClient';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

interface FileItem {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  source_name: string;
  updated_at: string;
  paperless_id?: number;
}

interface FileListResponse {
  items: FileItem[];
  next_cursor: string | null;
}

const TYPE_ICONS: Record<string, string> = {
  'application/pdf': 'PDF',
  'text/plain': 'TXT',
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOC',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLS',
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getTypeLabel(mime: string): string {
  return TYPE_ICONS[mime] ?? mime.split('/').pop()?.toUpperCase()?.slice(0, 4) ?? '?';
}

export function FilesScreen() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchFiles = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.request<FileListResponse>({
        path: '/files?limit=50',
      });
      setFiles(data.items);
    } catch {
      // Connectivity banner handles offline
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleFilePress = useCallback((file: FileItem) => {
    if (file.paperless_id) {
      const url = `${apiClient.getBaseUrl().replace('/api/v1', '')}/paperless/documents/${file.paperless_id}/`;
      Linking.openURL(url).catch(() => {});
    }
  }, []);

  const renderFile = useCallback(
    ({item}: {item: FileItem}) => (
      <TouchableOpacity
        style={styles.fileRow}
        onPress={() => handleFilePress(item)}
        accessibilityLabel={`${item.filename}, ${getTypeLabel(item.mime_type)}, ${formatSize(item.size_bytes)}`}
        accessibilityRole="button">
        <View style={styles.typeIcon}>
          <Text style={styles.typeText}>{getTypeLabel(item.mime_type)}</Text>
        </View>
        <View style={styles.fileInfo}>
          <Text style={styles.fileName} numberOfLines={1}>
            {item.filename}
          </Text>
          <Text style={styles.fileMeta}>
            {formatSize(item.size_bytes)} {' \u2022 '} {item.source_name}
            {' \u2022 '} {new Date(item.updated_at).toLocaleDateString()}
          </Text>
        </View>
      </TouchableOpacity>
    ),
    [handleFilePress],
  );

  const keyExtractor = useCallback((item: FileItem) => item.id, []);

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />
      <View style={styles.header}>
        <Text style={styles.heading} accessibilityRole="header">
          Files
        </Text>
      </View>

      {isLoading && files.length === 0 ? (
        <View style={styles.skeletons}>
          <Skeleton height={56} style={{marginHorizontal: sp(4), marginBottom: sp(2)}} />
          <Skeleton height={56} style={{marginHorizontal: sp(4), marginBottom: sp(2)}} />
          <Skeleton height={56} style={{marginHorizontal: sp(4)}} />
        </View>
      ) : (
        <FlatList
          data={files}
          renderItem={renderFile}
          keyExtractor={keyExtractor}
          ListEmptyComponent={
            <EmptyState
              title="No files yet"
              subtitle="Files will appear here after document ingestion."
            />
          }
          refreshControl={
            <RefreshControl refreshing={isLoading} onRefresh={fetchFiles} tintColor={Colors.primary} />
          }
          contentContainerStyle={files.length === 0 ? styles.emptyList : styles.list}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
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
  list: {paddingBottom: sp(8)},
  emptyList: {flexGrow: 1},
  fileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: sp(4),
    paddingVertical: sp(3),
    backgroundColor: Colors.white,
  },
  typeIcon: {
    width: 40,
    height: 40,
    borderRadius: Radius.md,
    backgroundColor: Colors.primarySurface,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: sp(3),
  },
  typeText: {
    ...Typography.caption,
    color: Colors.primary,
    fontWeight: '700',
  },
  fileInfo: {flex: 1},
  fileName: {...Typography.body, color: Colors.neutral900, fontWeight: '500'},
  fileMeta: {...Typography.caption, color: Colors.neutral500, marginTop: 2},
  separator: {height: 1, backgroundColor: Colors.neutral100, marginLeft: sp(4) + 40 + sp(3)},
  skeletons: {paddingTop: sp(3)},
});
