/**
 * ReviewQueueScreen — swipe-based face cluster review (S16-006).
 *
 * Card-stack UI: one cluster at a time.
 * Swipe right → confirm top candidate
 * Swipe left  → reject (not a person)
 * Tap skip    → skip for 24h
 * Tap candidate pill → switch active candidate
 */

import React, {useCallback, useState} from 'react';
import {
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {Badge} from '../components/ui/Badge';
import {EmptyState} from '../components/ui/EmptyState';
import {Skeleton} from '../components/ui/Skeleton';
import {useReviewQueue} from '../hooks/useReviewQueue';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

interface Props {
  onBack?: () => void;
}

export function ReviewQueueScreen({onBack}: Props) {
  const {clusters, currentIndex, total, isLoading, confirm, reject, skip, refresh} =
    useReviewQueue();
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);

  const current = clusters[0] ?? null;
  const activeCandidate =
    selectedCandidate ??
    current?.top_candidate?.person_id ??
    null;
  const activeName =
    selectedCandidate
      ? current?.other_candidates.find(c => c.person_id === selectedCandidate)?.display_name ??
        current?.top_candidate?.display_name ??
        'Unknown'
      : current?.top_candidate?.display_name ?? 'Unknown';

  const handleConfirm = useCallback(async () => {
    if (!activeCandidate || !current) return;
    await confirm(activeCandidate);
    setSelectedCandidate(null);
  }, [activeCandidate, current, confirm]);

  const handleReject = useCallback(async () => {
    await reject();
    setSelectedCandidate(null);
  }, [reject]);

  const handleSkip = useCallback(async () => {
    await skip();
    setSelectedCandidate(null);
  }, [skip]);

  const remaining = clusters.length;

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
        <View style={styles.headerRow}>
          <Text style={styles.heading} accessibilityRole="header">
            Review Queue
          </Text>
          <Text style={styles.progress}>
            {remaining > 0 ? `${remaining} remaining` : ''}
          </Text>
        </View>
      </View>

      {isLoading ? (
        <View style={styles.cardContainer}>
          <Skeleton height={200} style={{marginHorizontal: sp(4), borderRadius: Radius.lg}} />
        </View>
      ) : !current ? (
        <EmptyState
          title="All caught up!"
          subtitle="No face clusters to review right now."
          actionLabel="Refresh"
          onAction={refresh}
        />
      ) : (
        <View style={styles.cardContainer}>
          {/* Cluster card */}
          <View style={styles.clusterCard}>
            {/* Sample faces grid (placeholder) */}
            <View style={styles.faceGrid}>
              {current.sample_face_ids.slice(0, 6).map((fid, i) => (
                <View key={fid} style={styles.facePlaceholder}>
                  <Text style={styles.faceText}>{i + 1}</Text>
                </View>
              ))}
            </View>

            {/* Candidate info */}
            <View style={styles.candidateSection}>
              <Text style={styles.candidateLabel}>Who is this?</Text>
              <View style={styles.candidateRow}>
                <Text style={styles.candidateName}>{activeName}</Text>
                {current.top_candidate && (
                  <Badge
                    level={
                      current.top_candidate.confidence >= 0.8
                        ? 'high'
                        : current.top_candidate.confidence >= 0.5
                        ? 'medium'
                        : 'low'
                    }
                  />
                )}
              </View>
              <Text style={styles.faceCount}>
                {current.face_count} face{current.face_count !== 1 ? 's' : ''} in this cluster
              </Text>
            </View>

            {/* Other candidates */}
            {current.other_candidates.length > 0 && (
              <View style={styles.otherCandidates}>
                <Text style={styles.otherLabel}>Other matches:</Text>
                <View style={styles.pillRow}>
                  {current.other_candidates.map(c => (
                    <TouchableOpacity
                      key={c.person_id}
                      style={[
                        styles.pill,
                        selectedCandidate === c.person_id && styles.pillSelected,
                      ]}
                      onPress={() =>
                        setSelectedCandidate(
                          selectedCandidate === c.person_id ? null : c.person_id,
                        )
                      }
                      accessibilityLabel={`Select ${c.display_name}`}>
                      <Text
                        style={[
                          styles.pillText,
                          selectedCandidate === c.person_id && styles.pillTextSelected,
                        ]}>
                        {c.display_name}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            )}
          </View>

          {/* Action buttons */}
          <View style={styles.actionRow}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.rejectBtn]}
              onPress={handleReject}
              accessibilityLabel="Reject — not a person"
              accessibilityRole="button">
              <Text style={styles.rejectText}>Not a person</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionBtn, styles.skipBtn]}
              onPress={handleSkip}
              accessibilityLabel="Skip for now"
              accessibilityRole="button">
              <Text style={styles.skipText}>Skip</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.actionBtn, styles.confirmBtn]}
              onPress={handleConfirm}
              accessibilityLabel={`Confirm as ${activeName}`}
              accessibilityRole="button">
              <Text style={styles.confirmText}>Confirm</Text>
            </TouchableOpacity>
          </View>
        </View>
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
    paddingBottom: sp(2),
  },
  backBtn: {paddingHorizontal: sp(4), paddingTop: sp(2)},
  backText: {...Typography.body, color: Colors.primary},
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: sp(4),
    paddingTop: sp(2),
  },
  heading: {...Typography.h2, color: Colors.neutral900},
  progress: {...Typography.caption, color: Colors.neutral500},
  cardContainer: {flex: 1, padding: sp(4)},
  clusterCard: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: sp(4),
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 4,
  },
  faceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: sp(1),
    marginBottom: sp(4),
  },
  facePlaceholder: {
    width: 64,
    height: 64,
    borderRadius: Radius.md,
    backgroundColor: Colors.neutral200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  faceText: {...Typography.caption, color: Colors.neutral400},
  candidateSection: {marginBottom: sp(3)},
  candidateLabel: {...Typography.caption, color: Colors.neutral500, marginBottom: sp(1)},
  candidateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: sp(2),
  },
  candidateName: {...Typography.h2, color: Colors.neutral900},
  faceCount: {...Typography.small, color: Colors.neutral500, marginTop: sp(1)},
  otherCandidates: {
    borderTopWidth: 1,
    borderTopColor: Colors.neutral100,
    paddingTop: sp(3),
  },
  otherLabel: {...Typography.caption, color: Colors.neutral500, marginBottom: sp(2)},
  pillRow: {flexDirection: 'row', flexWrap: 'wrap', gap: sp(2)},
  pill: {
    paddingHorizontal: sp(3),
    paddingVertical: sp(1),
    borderRadius: Radius.full,
    backgroundColor: Colors.neutral100,
  },
  pillSelected: {backgroundColor: Colors.primarySurface},
  pillText: {...Typography.small, color: Colors.neutral700},
  pillTextSelected: {color: Colors.primary, fontWeight: '600'},
  actionRow: {
    flexDirection: 'row',
    marginTop: sp(4),
    gap: sp(3),
  },
  actionBtn: {
    flex: 1,
    height: 48,
    borderRadius: Radius.lg,
    justifyContent: 'center',
    alignItems: 'center',
  },
  rejectBtn: {backgroundColor: Colors.errorSurface},
  rejectText: {...Typography.body, color: Colors.error, fontWeight: '600'},
  skipBtn: {backgroundColor: Colors.neutral100},
  skipText: {...Typography.body, color: Colors.neutral600, fontWeight: '500'},
  confirmBtn: {backgroundColor: Colors.primary},
  confirmText: {...Typography.body, color: Colors.white, fontWeight: '600'},
});
