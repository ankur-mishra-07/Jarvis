/**
 * J.A.R.V.I.S. WebSocket client — real-time voice streaming.
 */

import { WSMessage, ConnectionStatus } from '../types';

type MessageHandler = (msg: WSMessage) => void;
type StatusHandler = (status: ConnectionStatus) => void;

class JarvisWebSocket {
  private ws: WebSocket | null = null;
  private serverUrl: string = '';
  private apiKey: string = '';
  private onMessage: MessageHandler | null = null;
  private onStatusChange: StatusHandler | null = null;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private _status: ConnectionStatus = 'disconnected';

  configure(serverUrl: string, apiKey: string) {
    this.serverUrl = serverUrl.replace(/\/+$/, '').replace(/^http/, 'ws');
    this.apiKey = apiKey;
  }

  setMessageHandler(handler: MessageHandler) {
    this.onMessage = handler;
  }

  setStatusHandler(handler: StatusHandler) {
    this.onStatusChange = handler;
  }

  get status(): ConnectionStatus {
    return this._status;
  }

  private setStatus(status: ConnectionStatus) {
    this._status = status;
    this.onStatusChange?.(status);
  }

  // ─── Connection ─────────────────────────────────────────────────────────

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.setStatus('connecting');
    const wsUrl = `${this.serverUrl}/ws/voice?api_key=${this.apiKey}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.setStatus('connected');
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          this.onMessage?.(msg);
        } catch (e) {
          console.warn('[WS] Failed to parse message:', e);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error);
        this.setStatus('error');
      };

      this.ws.onclose = (event) => {
        console.log(`[WS] Closed: ${event.code} ${event.reason}`);
        this.setStatus('disconnected');
        this.ws = null;
        this.scheduleReconnect();
      };
    } catch (e) {
      console.error('[WS] Connection failed:', e);
      this.setStatus('error');
      this.scheduleReconnect();
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
    this.ws?.close(1000, 'Client disconnect');
    this.ws = null;
    this.setStatus('disconnected');
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  // ─── Send Messages ────────────────────────────────────────────────────

  sendText(text: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Not connected, cannot send');
      return;
    }

    this.ws.send(JSON.stringify({ type: 'text', text }));
  }

  sendAudioChunk(pcmBase64: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    this.ws.send(JSON.stringify({ type: 'audio', data: pcmBase64 }));
  }

  sendAudioBytes(bytes: ArrayBuffer) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    this.ws.send(bytes);
  }

  sendEndOfSpeech() {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    this.ws.send(JSON.stringify({ type: 'end_of_speech' }));
  }

  sendPing() {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: 'ping' }));
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new JarvisWebSocket();
export default wsClient;
