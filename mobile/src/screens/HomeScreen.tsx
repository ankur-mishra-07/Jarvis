import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, FlatList, TextInput, TouchableOpacity,
  StyleSheet, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useChat } from '../store/chatStore';
import { useSettings } from '../store/settingsStore';
import { useVoice } from '../hooks/useVoice';
import ChatBubble from '../components/ChatBubble';
import VoiceButton from '../components/VoiceButton';
import ConnectionStatusBar from '../components/StatusBar';
import api from '../services/api';
import { StatusResponse } from '../types';

export default function HomeScreen({ navigation }: any) {
  const { messages, connectionStatus, isProcessing, currentTranscript } = useChat();
  const { serverUrl, apiKey } = useSettings();
  const { startRecording, stopAndSend, sendText, cancelRecording } = useVoice();

  const [textInput, setTextInput] = useState('');
  const [serverStatus, setServerStatus] = useState<StatusResponse | null>(null);
  const flatListRef = useRef<FlatList>(null);

  // Configure API on settings change
  useEffect(() => {
    if (serverUrl && apiKey) {
      api.configure(serverUrl, apiKey);
      checkStatus();
    }
  }, [serverUrl, apiKey]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages]);

  const checkStatus = async () => {
    try {
      const status = await api.getStatus();
      setServerStatus(status);
      useChat.getState().setConnectionStatus('connected');
    } catch {
      useChat.getState().setConnectionStatus('disconnected');
    }
  };

  const handleSendText = () => {
    const text = textInput.trim();
    if (!text) return;
    setTextInput('');
    sendText(text);
  };

  const isConfigured = serverUrl && apiKey;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.title}>J.A.R.V.I.S.</Text>
          <ConnectionStatusBar
            status={connectionStatus}
            backend={serverStatus?.active_backend || ''}
          />
        </View>
        <TouchableOpacity onPress={() => navigation.navigate('Settings')} style={styles.settingsBtn}>
          <Text style={styles.settingsIcon}>⚙️</Text>
        </TouchableOpacity>
      </View>

      {/* Not configured warning */}
      {!isConfigured && (
        <TouchableOpacity
          style={styles.configWarning}
          onPress={() => navigation.navigate('Settings')}
        >
          <Text style={styles.configWarningText}>
            Tap here to configure server URL and API key
          </Text>
        </TouchableOpacity>
      )}

      {/* Chat Messages */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <ChatBubble message={item} />}
        style={styles.chatList}
        contentContainerStyle={styles.chatContent}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>🤖</Text>
            <Text style={styles.emptyTitle}>J.A.R.V.I.S.</Text>
            <Text style={styles.emptySubtitle}>
              Hold the mic button to speak{'\n'}or type a command below
            </Text>
          </View>
        }
      />

      {/* Voice Button */}
      <VoiceButton
        onPressIn={startRecording}
        onPressOut={stopAndSend}
        isProcessing={isProcessing}
        transcript={currentTranscript}
      />

      {/* Text Input */}
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.textInput}
          value={textInput}
          onChangeText={setTextInput}
          placeholder="Type a command..."
          placeholderTextColor="#555"
          returnKeyType="send"
          onSubmitEditing={handleSendText}
          editable={!isProcessing}
        />
        <TouchableOpacity
          style={[styles.sendButton, !textInput.trim() && styles.sendButtonDisabled]}
          onPress={handleSendText}
          disabled={!textInput.trim() || isProcessing}
        >
          <Text style={styles.sendIcon}>➤</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a1a',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  headerLeft: {
    flex: 1,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1e90ff',
    letterSpacing: 2,
  },
  settingsBtn: {
    padding: 8,
  },
  settingsIcon: {
    fontSize: 22,
  },
  configWarning: {
    backgroundColor: '#332200',
    padding: 12,
    margin: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#665500',
  },
  configWarningText: {
    color: '#ffcc00',
    textAlign: 'center',
    fontSize: 13,
  },
  chatList: {
    flex: 1,
  },
  chatContent: {
    paddingVertical: 8,
    flexGrow: 1,
    justifyContent: 'flex-end',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingBottom: 40,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#1e90ff',
    letterSpacing: 4,
    marginBottom: 8,
  },
  emptySubtitle: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 22,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingBottom: Platform.OS === 'ios' ? 34 : 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#1a1a2e',
  },
  textInput: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#e0e0e0',
    borderWidth: 1,
    borderColor: '#2a2a4a',
  },
  sendButton: {
    marginLeft: 8,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#1e90ff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#1a1a2e',
  },
  sendIcon: {
    color: '#fff',
    fontSize: 18,
  },
});
