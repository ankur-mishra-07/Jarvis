/**
 * Audio recording & playback service using expo-av.
 */

import { Audio } from 'expo-av';

class AudioService {
  private recording: Audio.Recording | null = null;
  private sound: Audio.Sound | null = null;
  private _isRecording: boolean = false;

  get isRecording(): boolean {
    return this._isRecording;
  }

  // ─── Recording ────────────────────────────────────────────────────────

  async startRecording(): Promise<void> {
    try {
      // Request permissions
      const { granted } = await Audio.requestPermissionsAsync();
      if (!granted) {
        throw new Error('Microphone permission not granted');
      }

      // Configure audio mode
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      // Start recording — 16kHz mono WAV for best STT compatibility
      const { recording } = await Audio.Recording.createAsync({
        isMeteringEnabled: true,
        android: {
          extension: '.wav',
          outputFormat: Audio.AndroidOutputFormat.DEFAULT,
          audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
        },
        ios: {
          extension: '.wav',
          outputFormat: Audio.IOSOutputFormat.LINEARPCM,
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 256000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        web: {
          mimeType: 'audio/wav',
          bitsPerSecond: 256000,
        },
      });

      this.recording = recording;
      this._isRecording = true;
      console.log('[Audio] Recording started');
    } catch (error) {
      console.error('[Audio] Failed to start recording:', error);
      throw error;
    }
  }

  async stopRecording(): Promise<string | null> {
    if (!this.recording) return null;

    try {
      await this.recording.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
      });

      const uri = this.recording.getURI();
      this.recording = null;
      this._isRecording = false;

      console.log('[Audio] Recording stopped:', uri);
      return uri;
    } catch (error) {
      console.error('[Audio] Failed to stop recording:', error);
      this.recording = null;
      this._isRecording = false;
      return null;
    }
  }

  async cancelRecording(): Promise<void> {
    if (!this.recording) return;
    try {
      await this.recording.stopAndUnloadAsync();
    } catch {}
    this.recording = null;
    this._isRecording = false;
  }

  // ─── Playback ─────────────────────────────────────────────────────────

  async playAudio(url: string): Promise<void> {
    try {
      // Stop any current playback
      await this.stopPlayback();

      const { sound } = await Audio.Sound.createAsync(
        { uri: url },
        { shouldPlay: true }
      );

      this.sound = sound;

      // Auto-cleanup when done
      sound.setOnPlaybackStatusUpdate((status) => {
        if ('didJustFinish' in status && status.didJustFinish) {
          sound.unloadAsync();
          this.sound = null;
        }
      });
    } catch (error) {
      console.error('[Audio] Playback failed:', error);
    }
  }

  async playBase64Audio(base64Data: string): Promise<void> {
    try {
      await this.stopPlayback();

      const { sound } = await Audio.Sound.createAsync(
        { uri: `data:audio/wav;base64,${base64Data}` },
        { shouldPlay: true }
      );

      this.sound = sound;

      sound.setOnPlaybackStatusUpdate((status) => {
        if ('didJustFinish' in status && status.didJustFinish) {
          sound.unloadAsync();
          this.sound = null;
        }
      });
    } catch (error) {
      console.error('[Audio] Base64 playback failed:', error);
    }
  }

  async stopPlayback(): Promise<void> {
    if (this.sound) {
      try {
        await this.sound.stopAsync();
        await this.sound.unloadAsync();
      } catch {}
      this.sound = null;
    }
  }
}

export const audioService = new AudioService();
export default audioService;
