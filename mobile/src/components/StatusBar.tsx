import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ConnectionStatus } from '../types';

interface Props {
  status: ConnectionStatus;
  backend: string;
}

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  connected: '#00c853',
  connecting: '#ffc107',
  disconnected: '#ff5252',
  error: '#ff5252',
};

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connected: 'Connected',
  connecting: 'Connecting...',
  disconnected: 'Disconnected',
  error: 'Error',
};

export default function ConnectionStatusBar({ status, backend }: Props) {
  const color = STATUS_COLORS[status];

  return (
    <View style={styles.container}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.text, { color }]}>
        {STATUS_LABELS[status]}
      </Text>
      {backend && status === 'connected' && (
        <Text style={styles.backend}>| LLM: {backend}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
  },
  backend: {
    fontSize: 11,
    color: '#666',
    marginLeft: 8,
  },
});
