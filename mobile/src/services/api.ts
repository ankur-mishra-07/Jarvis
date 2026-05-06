/**
 * J.A.R.V.I.S. REST API client.
 */

import { ChatRequest, ChatResponse, CommandResponse, StatusResponse, ConfigResponse } from '../types';

class JarvisAPI {
  private baseUrl: string = '';
  private apiKey: string = '';

  configure(serverUrl: string, apiKey: string) {
    // Ensure no trailing slash
    this.baseUrl = serverUrl.replace(/\/+$/, '');
    this.apiKey = apiKey;
  }

  private get headers() {
    return {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey,
    };
  }

  // ─── Chat (text) ────────────────────────────────────────────────────────

  async chat(text: string): Promise<ChatResponse> {
    const resp = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ text } as ChatRequest),
    });

    if (!resp.ok) {
      throw new Error(`Chat failed: ${resp.status} ${resp.statusText}`);
    }

    return resp.json();
  }

  // ─── Command (audio upload) ─────────────────────────────────────────────

  async sendAudio(audioUri: string, format: string = 'wav'): Promise<CommandResponse> {
    const formData = new FormData();

    // React Native file upload
    formData.append('audio', {
      uri: audioUri,
      type: `audio/${format}`,
      name: `recording.${format}`,
    } as any);
    formData.append('format', format);

    const resp = await fetch(`${this.baseUrl}/api/command`, {
      method: 'POST',
      headers: {
        'X-API-Key': this.apiKey,
      },
      body: formData,
    });

    if (!resp.ok) {
      throw new Error(`Command failed: ${resp.status}`);
    }

    return resp.json();
  }

  // ─── Status ─────────────────────────────────────────────────────────────

  async getStatus(): Promise<StatusResponse> {
    const resp = await fetch(`${this.baseUrl}/api/status`, {
      headers: this.headers,
    });

    if (!resp.ok) {
      throw new Error(`Status failed: ${resp.status}`);
    }

    return resp.json();
  }

  // ─── Config ─────────────────────────────────────────────────────────────

  async getConfig(): Promise<ConfigResponse> {
    const resp = await fetch(`${this.baseUrl}/api/config`, {
      headers: this.headers,
    });

    if (!resp.ok) {
      throw new Error(`Config failed: ${resp.status}`);
    }

    return resp.json();
  }

  // ─── Screenshot ─────────────────────────────────────────────────────────

  async getScreenshot(): Promise<string> {
    // Returns URL to screenshot image
    return `${this.baseUrl}/api/screenshot?api_key=${this.apiKey}`;
  }

  // ─── Audio playback URL ─────────────────────────────────────────────────

  getAudioUrl(path: string): string {
    if (path.startsWith('http')) return path;
    return `${this.baseUrl}${path}`;
  }

  // ─── Connection test ───────────────────────────────────────────────────

  async testConnection(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/`, { timeout: 5000 } as any);
      return resp.ok;
    } catch {
      return false;
    }
  }
}

export const api = new JarvisAPI();
export default api;
