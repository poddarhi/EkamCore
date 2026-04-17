/**
 * PersonDetailScreen — person profile with tabbed content (S16-006).
 *
 * Header: avatar + name + edit + actions
 * Tabs: Photos | Files | Events (placeholder content — wired to endpoints)
 */

import React, {useCallback, useEffect, useState} from 'react';
import {
  Alert,
  FlatList,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {EmptyState} from '../components/ui/EmptyState';
import * as peopleApi from '../api/endpoints/people';
import type {Person} from '../api/endpoints/people';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

type Tab = 'photos' | 'files' | 'events';

interface Props {
  personId: string;
  onBack?: () => void;
}

export function PersonDetailScreen({personId, onBack}: Props) {
  const [person, setPerson] = useState<Person | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('photos');
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState('');

  // Tab data
  const [photos, setPhotos] = useState<{id: string; taken_at: string | null}[]>([]);
  const [files, setFiles] = useState<{id: string; filename: string; mime_type: string}[]>([]);
  const [events, setEvents] = useState<{id: string; title: string; start_at: string}[]>([]);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const p = await peopleApi.getPerson(personId);
        setPerson(p);
        setEditName(p.display_name);
      } catch {
        // Error handled by empty state
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [personId]);

  useEffect(() => {
    async function loadTab() {
      try {
        if (activeTab === 'photos') {
          const res = await peopleApi.getPersonPhotos(personId);
          setPhotos(res.items);
        } else if (activeTab === 'files') {
          const res = await peopleApi.getPersonFiles(personId);
          setFiles(res.items);
        } else if (activeTab === 'events') {
          const res = await peopleApi.getPersonEvents(personId);
          setEvents(res.items);
        }
      } catch {
        // Silent fail
      }
    }
    loadTab();
  }, [personId, activeTab]);

  const handleRename = useCallback(async () => {
    if (!editName.trim() || !person) return;
    try {
      const updated = await peopleApi.renamePerson(person.id, editName.trim());
      setPerson(updated);
      setIsEditing(false);
    } catch {
      Alert.alert('Error', 'Could not rename person.');
    }
  }, [editName, person]);

  const handleDelete = useCallback(async () => {
    if (!person) return;
    Alert.alert(
      'Delete Person',
      `Are you sure you want to delete ${person.display_name}?`,
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await peopleApi.deletePerson(person.id);
              onBack?.();
            } catch {
              Alert.alert('Error', 'Could not delete person.');
            }
          },
        },
      ],
    );
  }, [person, onBack]);

  if (isLoading || !person) {
    return (
      <SafeAreaView style={styles.root}>
        <EmptyState title={isLoading ? 'Loading...' : 'Person not found'} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />

      {/* Header */}
      <View style={styles.header}>
        {onBack && (
          <TouchableOpacity onPress={onBack} style={styles.backBtn} accessibilityLabel="Back">
            <Text style={styles.backText}>{'<'} Back</Text>
          </TouchableOpacity>
        )}

        <View style={styles.profileRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {person.display_name.charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            {isEditing ? (
              <View style={styles.editRow}>
                <TextInput
                  style={styles.editInput}
                  value={editName}
                  onChangeText={setEditName}
                  autoFocus
                  returnKeyType="done"
                  onSubmitEditing={handleRename}
                  accessibilityLabel="Person name"
                />
                <TouchableOpacity onPress={handleRename} style={styles.saveBtn}>
                  <Text style={styles.saveBtnText}>Save</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <TouchableOpacity onPress={() => setIsEditing(true)}>
                <Text style={styles.profileName}>{person.display_name}</Text>
              </TouchableOpacity>
            )}
            <Text style={styles.profileMeta}>
              {person.trust_source}
              {person.face_count != null && ` \u2022 ${person.face_count} faces`}
            </Text>
          </View>
        </View>

        {/* Actions */}
        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => setIsEditing(true)}
            accessibilityLabel="Rename">
            <Text style={styles.actionText}>Rename</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionBtn, styles.actionDanger]}
            onPress={handleDelete}
            accessibilityLabel="Delete person">
            <Text style={styles.actionDangerText}>Delete</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab bar */}
      <View style={styles.tabBar}>
        {(['photos', 'files', 'events'] as Tab[]).map(tab => (
          <TouchableOpacity
            key={tab}
            style={[styles.tab, activeTab === tab && styles.tabActive]}
            onPress={() => setActiveTab(tab)}
            accessibilityRole="tab"
            accessibilityState={{selected: activeTab === tab}}>
            <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab content */}
      {activeTab === 'photos' && (
        <FlatList
          data={photos}
          keyExtractor={item => item.id}
          renderItem={({item}) => (
            <View style={styles.listRow}>
              <Text style={styles.listText}>
                Photo {item.taken_at ? new Date(item.taken_at).toLocaleDateString() : 'Unknown date'}
              </Text>
            </View>
          )}
          ListEmptyComponent={<EmptyState title="No photos" />}
          contentContainerStyle={photos.length === 0 ? styles.emptyList : undefined}
        />
      )}
      {activeTab === 'files' && (
        <FlatList
          data={files}
          keyExtractor={item => item.id}
          renderItem={({item}) => (
            <View style={styles.listRow}>
              <Text style={styles.listText}>{item.filename}</Text>
              <Text style={styles.listMeta}>{item.mime_type}</Text>
            </View>
          )}
          ListEmptyComponent={<EmptyState title="No files" />}
          contentContainerStyle={files.length === 0 ? styles.emptyList : undefined}
        />
      )}
      {activeTab === 'events' && (
        <FlatList
          data={events}
          keyExtractor={item => item.id}
          renderItem={({item}) => (
            <View style={styles.listRow}>
              <Text style={styles.listText}>{item.title}</Text>
              <Text style={styles.listMeta}>{new Date(item.start_at).toLocaleDateString()}</Text>
            </View>
          )}
          ListEmptyComponent={<EmptyState title="No events" />}
          contentContainerStyle={events.length === 0 ? styles.emptyList : undefined}
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
  backBtn: {paddingHorizontal: sp(4), paddingTop: sp(2)},
  backText: {...Typography.body, color: Colors.primary},
  profileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: sp(4),
    paddingTop: sp(3),
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: Colors.primarySurface,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: sp(4),
  },
  avatarText: {...Typography.display, color: Colors.primary, fontSize: 28},
  profileInfo: {flex: 1},
  profileName: {...Typography.h2, color: Colors.neutral900},
  profileMeta: {...Typography.small, color: Colors.neutral500, marginTop: 2},
  editRow: {flexDirection: 'row', alignItems: 'center'},
  editInput: {
    flex: 1,
    height: 36,
    borderWidth: 1,
    borderColor: Colors.primary,
    borderRadius: Radius.md,
    paddingHorizontal: sp(2),
    ...Typography.body,
    color: Colors.neutral900,
  },
  saveBtn: {marginLeft: sp(2), paddingHorizontal: sp(3), paddingVertical: sp(1)},
  saveBtnText: {...Typography.body, color: Colors.primary, fontWeight: '600'},
  actions: {
    flexDirection: 'row',
    paddingHorizontal: sp(4),
    marginTop: sp(3),
    gap: sp(2),
  },
  actionBtn: {
    paddingHorizontal: sp(3),
    paddingVertical: sp(1),
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.neutral200,
  },
  actionText: {...Typography.caption, color: Colors.neutral700},
  actionDanger: {borderColor: Colors.error},
  actionDangerText: {...Typography.caption, color: Colors.error},
  tabBar: {
    flexDirection: 'row',
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral200,
  },
  tab: {
    flex: 1,
    paddingVertical: sp(3),
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {borderBottomColor: Colors.primary},
  tabText: {...Typography.small, color: Colors.neutral500, fontWeight: '500'},
  tabTextActive: {color: Colors.primary, fontWeight: '600'},
  listRow: {
    paddingHorizontal: sp(4),
    paddingVertical: sp(3),
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral100,
  },
  listText: {...Typography.body, color: Colors.neutral900},
  listMeta: {...Typography.caption, color: Colors.neutral500, marginTop: 2},
  emptyList: {flexGrow: 1},
});
