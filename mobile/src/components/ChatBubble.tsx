import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { ChatMessage } from '../types';
import audioService from '../services/audio';
import api from '../services/api';

interface Props {
  message: ChatMessage;
}

export default function ChatBubble({ message }: Props) {
  const isUser = message.role === 'user';

  const playAudio = async () => {
    if (message.audioUrl) {
      const url = api.getAudioUrl(message.audioUrl);
      await audioService.playAudio(url);
    }
  };

  return (
    <View style={[styles.container, isUser ? styles.userContainer : styles.assistantContainer]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.assistantBubble]}>
        <Text style={[styles.text, isUser ? styles.userText : styles.assistantText]}>
          {message.text}
        </Text>

        {message.audioUrl && (
          <TouchableOpacity onPress={playAudio} style={styles.audioButton}>
            <Text style={styles.audioIcon}>🔊</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.timestamp}>
        {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
    marginHorizontal: 12,
  },
  userContainer: {
    alignItems: 'flex-end',
  },
  assistantContainer: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    flexDirection: 'row',
    alignItems: 'center',
  },
  userBubble: {
    backgroundColor: '#1e90ff',
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: '#1a1a2e',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: '#2a2a4a',
  },
  text: {
    fontSize: 15,
    lineHeight: 20,
    flex: 1,
  },
  userText: {
    color: '#ffffff',
  },
  assistantText: {
    color: '#e0e0e0',
  },
  audioButton: {
    marginLeft: 8,
    padding: 4,
  },
  audioIcon: {
    fontSize: 16,
  },
  timestamp: {
    fontSize: 10,
    color: '#666',
    marginTop: 2,
    marginHorizontal: 4,
  },
});
