/**
 * Persistent settings store (Zustand + AsyncStorage).
 */

import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Settings } from '../types';

interface SettingsState extends Settings {
  loaded: boolean;
  load: () => Promise<void>;
  save: () => Promise<void>;
  update: (partial: Partial<Settings>) => void;
}

const STORAGE_KEY = 'jarvis_settings';

const DEFAULTS: Settings = {
  serverUrl: 'http://192.168.1.100:8786',  // User must set their server IP
  apiKey: '',
  pushToTalk: true,
  playAudioResponse: true,
};

export const useSettings = create<SettingsState>((set, get) => ({
  ...DEFAULTS,
  loaded: false,

  load: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<Settings>;
        set({ ...DEFAULTS, ...saved, loaded: true });
      } else {
        set({ loaded: true });
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
      set({ loaded: true });
    }
  },

  save: async () => {
    try {
      const { loaded, load, save, update, ...settings } = get();
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch (e) {
      console.error('Failed to save settings:', e);
    }
  },

  update: (partial: Partial<Settings>) => {
    set(partial);
    // Auto-save after update
    setTimeout(() => get().save(), 100);
  },
}));
