import React from 'react';
import {FlatList, SafeAreaView, StyleSheet, Text, View} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {Colors, Typography, sp} from '../design-system/tokens';

export function TodayScreen() {
  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />
      <View style={styles.header}>
        <Text style={styles.heading} accessibilityRole="header">
          Today
        </Text>
      </View>
      <FlatList
        data={[]}
        renderItem={() => null}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No cards yet.</Text>
          </View>
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  header: {
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
    paddingBottom: sp(3),
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral200,
  },
  heading: {
    ...Typography.h1,
    color: Colors.neutral900,
  },
  list: {flexGrow: 1},
  empty: {flex: 1, justifyContent: 'center', alignItems: 'center', padding: sp(8)},
  emptyText: {...Typography.body, color: Colors.neutral500},
});
