import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  StyleSheet, Alert, Platform, Switch,
} from 'react-native';
import { useSettings } from '../store/settingsStore';
import api from '../services/api';

export default function SettingsScreen({ navigation }: any) {
  const settings = useSettings();
  const [serverUrl, setServerUrl] = useState(settings.serverUrl);
  const [apiKey, setApiKey] = useState(settings.apiKey);
  const [testing, setTesting] = useState(false);

  const handleSave = () => {
    settings.update({
      serverUrl: serverUrl.trim(),
      apiKey: apiKey.trim(),
    });
    Alert.alert('Saved', 'Settings updated successfully.');
  };

  const handleTest = async () => {
    setTesting(true);
    api.configure(serverUrl.trim(), apiKey.trim());

    try {
      const status = await api.getStatus();
      Alert.alert(
        'Connected!',
        `Server: ${status.version}\nLLM: ${status.active_backend}\nOwner: ${status.owner_name}`,
      );
    } catch (error: any) {
      Alert.alert('Connection Failed', error.message || 'Cannot reach server');
    } finally {
      setTesting(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Server Connection</Text>

      <Text style={styles.label}>Server URL</Text>
      <TextInput
        style={styles.input}
        value={serverUrl}
        onChangeText={setServerUrl}
        placeholder="http://192.168.1.100:8786"
        placeholderTextColor="#555"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />
      <Text style={styles.hint}>
        Your Mac/Pi IP address + port 8786
      </Text>

      <Text style={styles.label}>API Key</Text>
      <TextInput
        style={styles.input}
        value={apiKey}
        onChangeText={setApiKey}
        placeholder="your-server-api-key"
        placeholderTextColor="#555"
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />
      <Text style={styles.hint}>
        Set in config.json as "server_api_key"
      </Text>

      {/* Test & Save buttons */}
      <View style={styles.buttonRow}>
        <TouchableOpacity
          style={[styles.button, styles.testButton]}
          onPress={handleTest}
          disabled={testing}
        >
          <Text style={styles.buttonText}>
            {testing ? 'Testing...' : 'Test Connection'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.button, styles.saveButton]} onPress={handleSave}>
          <Text style={styles.buttonText}>Save</Text>
        </TouchableOpacity>
      </View>

      {/* Audio Settings */}
      <Text style={[styles.sectionTitle, { marginTop: 32 }]}>Audio</Text>

      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>Push to Talk</Text>
        <Switch
          value={settings.pushToTalk}
          onValueChange={(val) => settings.update({ pushToTalk: val })}
          trackColor={{ false: '#333', true: '#1e90ff' }}
        />
      </View>

      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>Play Audio Responses</Text>
        <Switch
          value={settings.playAudioResponse}
          onValueChange={(val) => settings.update({ playAudioResponse: val })}
          trackColor={{ false: '#333', true: '#1e90ff' }}
        />
      </View>

      {/* Info */}
      <View style={styles.infoBox}>
        <Text style={styles.infoTitle}>How to connect</Text>
        <Text style={styles.infoText}>
          1. Start Jarvis server: python jarvis.py --server{'\n'}
          2. Find your Mac's IP: ifconfig | grep inet{'\n'}
          3. Enter the IP above with port 8786{'\n'}
          4. Set API key (same as config.json server_api_key){'\n'}
          5. Tap "Test Connection" to verify
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a1a',
  },
  content: {
    padding: 20,
    paddingTop: Platform.OS === 'ios' ? 60 : 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1e90ff',
    marginBottom: 16,
    letterSpacing: 1,
  },
  label: {
    fontSize: 14,
    color: '#aaa',
    marginBottom: 6,
    marginTop: 12,
  },
  input: {
    backgroundColor: '#1a1a2e',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#e0e0e0',
    borderWidth: 1,
    borderColor: '#2a2a4a',
  },
  hint: {
    fontSize: 11,
    color: '#555',
    marginTop: 4,
  },
  buttonRow: {
    flexDirection: 'row',
    marginTop: 20,
    gap: 12,
  },
  button: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
  },
  testButton: {
    backgroundColor: '#2a2a4a',
    borderWidth: 1,
    borderColor: '#1e90ff',
  },
  saveButton: {
    backgroundColor: '#1e90ff',
  },
  buttonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2e',
  },
  switchLabel: {
    fontSize: 15,
    color: '#e0e0e0',
  },
  infoBox: {
    backgroundColor: '#0d1b2a',
    borderRadius: 10,
    padding: 16,
    marginTop: 24,
    borderWidth: 1,
    borderColor: '#1a3050',
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1e90ff',
    marginBottom: 8,
  },
  infoText: {
    fontSize: 12,
    color: '#888',
    lineHeight: 20,
  },
});
