import type { DeviceAdapter } from '../adapters/DeviceAdapter';
import type { HealthKitDeviceAdapter } from '../adapters/HealthKitDeviceAdapter';
import type { DeliverFn } from '../engine/notify';
import type { FamilyLinkTransport } from '../family/FamilyService';
import type { ChatMessage } from '../types';
export interface VoicePort {
  status(): {available:boolean; phase:string; detail?:string; outputAvailable?:boolean; microphone?:string};
  recognize(input: unknown): Promise<string>;
  speak(text:string, config:{language:'zh-CN'; rate:0.9}): Promise<void>;
  cancel(): void;
}
export const mainSpeechText = (message: ChatMessage) => message.blocks?.find(b => b.kind === 'main')?.text ?? message.text;
export interface SyncPort extends FamilyLinkTransport {
  readonly via: 'local' | 'peer';
  readonly role: 'elder' | 'family';
  status(): {mode:'local-only'|'connecting'|'cross-device'|'failed'; detail:string; peerId:string|null};
  close(): void;
}
export interface ProductExtensions {
  devices?: Record<string, DeviceAdapter>;
  healthkit?: HealthKitDeviceAdapter;
  voice?: VoicePort;
  delivery?: DeliverFn;
  sync?: (owner:string) => SyncPort;
}
