import type { VoicePort } from '../product/ExtensionPorts';
type SpeechRecognitionResultEvent = Event & {
  results: {
    length: number;
    [index: number]: { [index: number]: { transcript: string } };
  };
};
type SpeechRecognitionErrorEvent = Event & { error?: string };
export type SpeechRecognitionLike = {
  onstart?: (() => void) | null;
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  start: () => void;
  stop: () => void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}


/** Extracted from VoiceListeningDialog; no microphone is opened until startListening. */
export function startListening(callbacks: {phase(value:string):void; transcript(value:string):void; error(value:string):void; close():void; text(value:string):void}) {
    let disposed = false,
      failed = false,
      sent = false,
      words = '';
    let watchdog: ReturnType<typeof setTimeout>;
    callbacks.phase('starting');
    callbacks.transcript('');
    callbacks.error('');
    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    const rec = Ctor ? new Ctor() : null;
    function fail(message: string) {
      if (disposed) return;
      failed = true;
      clearTimeout(watchdog);
      callbacks.error(message);
      callbacks.phase('error');
    }
    const cancel = () => {
      disposed = true;
      clearTimeout(watchdog);
      try {
        rec?.stop();
      } catch {}
      callbacks.close();
    };
    const stop = () => {
      if (!rec || failed) return;
      callbacks.phase('finishing');
      rec.stop();
    };
    if (!rec) {
      fail('当前浏览器不支持语音识别。请返回输入文字，或使用手机键盘的听写功能。');
      return {stop, cancel, dispose: () => { disposed = true; }};
    }
    rec.lang = 'zh-CN';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onstart = () => {
      if (!disposed && !failed) {
        clearTimeout(watchdog);
        callbacks.phase('listening');
      }
    };
    rec.onresult = (event) => {
      if (disposed || failed) return;
      words = Array.from({ length: event.results.length }, (_, i) => event.results[i]?.[0]?.transcript ?? '')
        .join('')
        .trim();
      callbacks.transcript(words);
    };
    rec.onerror = (event) =>
      fail(
        event.error === 'not-allowed' || event.error === 'service-not-allowed'
          ? '麦克风或语音服务未获授权，请在浏览器设置中允许后重试。'
          : event.error === 'no-speech'
            ? '没有听清您的声音，请靠近麦克风再试一次。'
            : '语音识别暂不可用，请检查网络和麦克风，或返回输入文字。',
      );
    rec.onend = () => {
      clearTimeout(watchdog);
      if (disposed || failed || sent) return;
      if (!words) {
        fail('没有听到可识别的内容，请重试。');
        return;
      }
      sent = true;
      callbacks.close();
      callbacks.text(words);
    };
    watchdog = setTimeout(() => {
      fail('语音服务启动超时，请检查麦克风权限或返回输入文字。');
      try {
        rec.stop();
      } catch {}
    }, 15000);
    try {
      window.speechSynthesis?.cancel();
      rec.start();
    } catch {
      fail('无法启动语音服务，请重试或返回输入文字。');
    }
    return {stop, cancel, dispose: () => {
      disposed = true;
      clearTimeout(watchdog);
      rec.onend = null;
      rec.onresult = null;
      rec.onerror = null;
      rec.onstart = null;
      try {
        rec.stop();
      } catch {}
    }};
}
export function speakText(text: string) {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) throw new Error('TTS unavailable');
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.replace(/\n/g, '。'));
  utterance.lang = 'zh-CN'; utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

/** Browser host implements the same product port; desktop leaves unavailable until a native ASR is supplied. */
export class BrowserVoicePort implements VoicePort {
  private phase = 'idle'; private rejectPending?: (error:Error) => void; private handle?: ReturnType<typeof startListening>;
  status() {return {available:typeof window !== 'undefined' && Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition),phase:this.phase};}
  recognize(_input:unknown):Promise<string> {
    this.cancel();
    if (!this.status().available) return Promise.reject(new Error('ASR unavailable'));
    return new Promise((resolve,reject) => {
      this.rejectPending=reject;
      this.handle = startListening({phase:value => {this.phase=value;},transcript:() => {},
        error:message => {if(message) {this.phase='error';this.rejectPending=undefined; reject(new Error(message));}},
        close:() => {this.phase='idle';},text:words => {this.rejectPending=undefined;resolve(words);}});
    });
  }
  async speak(text:string,_config:{language:'zh-CN';rate:0.9}) {speakText(text);}
  cancel() {this.rejectPending?.(new Error('ASR cancelled'));this.rejectPending=undefined;this.handle?.dispose();this.handle=undefined;this.phase='idle';if(typeof window !== 'undefined') window.speechSynthesis?.cancel();}
}
