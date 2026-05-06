/**
 * Chat state management (Zustand).
 */

import { create } from 'zustand';
import { ChatMessage, ConnectionStatus } from '../types';

interface ChatState {
  messages: ChatMessage[];
  connectionStatus: ConnectionStatus;
  isProcessing: boolean;
  currentTranscript: string;

  addMessage: (role: 'user' | 'assistant', text: string, audioUrl?: string) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setProcessing: (processing: boolean) => void;
  setTranscript: (text: string) => void;
  clearMessages: () => void;
}

let _nextId = 0;

export const useChat = create<ChatState>((set) => ({
  messages: [],
  connectionStatus: 'disconnected',
  isProcessing: false,
  currentTranscript: '',

  addMessage: (role, text, audioUrl) => {
    const msg: ChatMessage = {
      id: `msg_${++_nextId}_${Date.now()}`,
      role,
      text,
      audioUrl,
      timestamp: Date.now(),
    };
    set((state) => ({
      messages: [...state.messages, msg],
    }));
  },

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setProcessing: (processing) => set({ isProcessing: processing }),
  setTranscript: (text) => set({ currentTranscript: text }),
  clearMessages: () => set({ messages: [], currentTranscript: '' }),
}));
