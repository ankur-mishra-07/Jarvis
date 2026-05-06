import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Animated } from 'react-native';

interface Props {
  onPressIn: () => void;
  onPressOut: () => void;
  isProcessing: boolean;
  transcript: string;
}

export default function VoiceButton({ onPressIn, onPressOut, isProcessing, transcript }: Props) {
  const [isPressed, setIsPressed] = useState(false);
  const scale = React.useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    setIsPressed(true);
    Animated.spring(scale, { toValue: 1.15, useNativeDriver: true }).start();
    onPressIn();
  };

  const handlePressOut = () => {
    setIsPressed(false);
    Animated.spring(scale, { toValue: 1, useNativeDriver: true }).start();
    onPressOut();
  };

  const getStatusText = () => {
    if (isProcessing) return 'Processing...';
    if (isPressed) return 'Listening...';
    if (transcript) return transcript;
    return 'Hold to speak';
  };

  return (
    <View style={styles.container}>
      {/* Status text */}
      <Text style={styles.statusText} numberOfLines={1}>
        {getStatusText()}
      </Text>

      {/* Voice button */}
      <Pressable
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isProcessing}
      >
        <Animated.View
          style={[
            styles.button,
            isPressed && styles.buttonActive,
            isProcessing && styles.buttonProcessing,
            { transform: [{ scale }] },
          ]}
        >
          <Text style={styles.buttonIcon}>
            {isProcessing ? '...' : isPressed ? '🎙️' : '🎤'}
          </Text>
        </Animated.View>
      </Pressable>

      {/* Outer ring animation */}
      {isPressed && (
        <View style={styles.ring} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
  },
  statusText: {
    color: '#888',
    fontSize: 13,
    marginBottom: 12,
  },
  button: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: '#1a1a2e',
    borderWidth: 2,
    borderColor: '#1e90ff',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowColor: '#1e90ff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
  },
  buttonActive: {
    backgroundColor: '#1e90ff',
    borderColor: '#4db8ff',
    shadowOpacity: 0.6,
  },
  buttonProcessing: {
    backgroundColor: '#2a2a4a',
    borderColor: '#555',
    opacity: 0.7,
  },
  buttonIcon: {
    fontSize: 28,
  },
  ring: {
    position: 'absolute',
    width: 96,
    height: 96,
    borderRadius: 48,
    borderWidth: 2,
    borderColor: 'rgba(30, 144, 255, 0.3)',
    top: 40,
  },
});
