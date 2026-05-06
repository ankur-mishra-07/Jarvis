/**
 * Voice interaction hook — manages record → send → receive → play cycle.
 */

import { useCallback, useRef } from 'react';
import { useChat } from '../store/chatStore';
import { useSettings } from '../store/settingsStore';
import api from '../services/api';
import audioService from '../services/audio';

export function useVoice() {
  const { addMessage, setProcessing, setTranscript } = useChat();
  const { playAudioResponse } = useSettings();
  const isRecordingRef = useRef(false);

  // ─── Push-to-Talk: Start ──────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (isRecordingRef.current) return;
    isRecordingRef.current = true;

    try {
      await audioService.startRecording();
    } catch (error) {
      console.error('Failed to start recording:', error);
      isRecordingRef.current = false;
    }
  }, []);

  // ─── Push-to-Talk: Stop & Send ────────────────────────────────────────

  const stopAndSend = useCallback(async () => {
    if (!isRecordingRef.current) return;
    isRecordingRef.current = false;

    const uri = await audioService.stopRecording();
    if (!uri) return;

    setProcessing(true);
    setTranscript('Processing...');

    try {
      const result = await api.sendAudio(uri, 'wav');

      if (result.transcript) {
        setTranscript(result.transcript);
        addMessage('user', result.transcript);
      }

      if (result.response) {
        addMessage('assistant', result.response, result.audio_url || undefined);

        // Auto-play TTS response
        if (playAudioResponse && result.audio_url) {
          const audioUrl = api.getAudioUrl(result.audio_url);
          await audioService.playAudio(audioUrl);
        }
      }
    } catch (error) {
      console.error('Voice command failed:', error);
      addMessage('assistant', 'Connection error. Check server status.');
    } finally {
      setProcessing(false);
      setTranscript('');
    }
  }, [addMessage, setProcessing, setTranscript, playAudioResponse]);

  // ─── Text Command ─────────────────────────────────────────────────────

  const sendText = useCallback(async (text: string) => {
    if (!text.trim()) return;

    addMessage('user', text);
    setProcessing(true);

    try {
      const result = await api.chat(text);

      if (result.response) {
        addMessage('assistant', result.response, result.audio_url || undefined);

        if (playAudioResponse && result.audio_url) {
          const audioUrl = api.getAudioUrl(result.audio_url);
          await audioService.playAudio(audioUrl);
        }
      }
    } catch (error) {
      console.error('Chat failed:', error);
      addMessage('assistant', 'Connection error. Check server status.');
    } finally {
      setProcessing(false);
    }
  }, [addMessage, setProcessing, playAudioResponse]);

  // ─── Cancel ───────────────────────────────────────────────────────────

  const cancelRecording = useCallback(async () => {
    isRecordingRef.current = false;
    await audioService.cancelRecording();
    setTranscript('');
  }, [setTranscript]);

  return {
    startRecording,
    stopAndSend,
    sendText,
    cancelRecording,
    isRecording: isRecordingRef.current,
  };
}
