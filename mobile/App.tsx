/**
 * J.A.R.V.I.S. Mobile — Main App Entry
 */

import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import HomeScreen from './src/screens/HomeScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { useSettings } from './src/store/settingsStore';
import api from './src/services/api';

const Stack = createNativeStackNavigator();

// Dark theme
const DarkTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: '#0a0a1a',
    card: '#0a0a1a',
    text: '#e0e0e0',
    border: '#1a1a2e',
    primary: '#1e90ff',
  },
};

export default function App() {
  const { load, serverUrl, apiKey } = useSettings();

  // Load persisted settings on app start
  useEffect(() => {
    load();
  }, []);

  // Configure API when settings are available
  useEffect(() => {
    if (serverUrl && apiKey) {
      api.configure(serverUrl, apiKey);
    }
  }, [serverUrl, apiKey]);

  return (
    <>
      <StatusBar style="light" />
      <NavigationContainer theme={DarkTheme}>
        <Stack.Navigator
          screenOptions={{
            headerStyle: { backgroundColor: '#0a0a1a' },
            headerTintColor: '#1e90ff',
            headerTitleStyle: { fontWeight: '700' },
          }}
        >
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{ headerShown: false }}
          />
          <Stack.Screen
            name="Settings"
            component={SettingsScreen}
            options={{ title: 'Settings' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </>
  );
}
