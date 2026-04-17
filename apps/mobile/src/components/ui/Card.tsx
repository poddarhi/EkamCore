/**
 * Card — base container with shadow/elevation (S16-004 / ART-05 §19).
 */
import React, {type ReactNode} from 'react';
import {Platform, StyleSheet, TouchableOpacity, View} from 'react-native';
import {Colors, Radius, sp} from '../../design-system/tokens';

interface Props {
  children: ReactNode;
  onPress?: () => void;
  testID?: string;
}

export function Card({children, onPress, testID}: Props) {
  if (onPress) {
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={onPress}
        activeOpacity={0.7}
        accessibilityRole="button"
        testID={testID}>
        {children}
      </TouchableOpacity>
    );
  }
  return (
    <View style={styles.card} testID={testID}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: sp(4),
    marginHorizontal: sp(4),
    marginBottom: sp(3),
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: {width: 0, height: 2},
        shadowOpacity: 0.06,
        shadowRadius: 6,
      },
      android: {
        elevation: 2,
      },
    }),
  },
});
