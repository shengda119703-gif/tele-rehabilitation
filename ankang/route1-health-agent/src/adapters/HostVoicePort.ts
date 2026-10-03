import type { VoicePort } from '../product/ExtensionPorts';

/** Only host I/O. All recognized text still follows ProductService's existing chat path. */
export class HostVoicePort implements VoicePort {
  private state: ReturnType<VoicePort['status']> = {available:false,phase:'unavailable',outputAvailable:false};
  constructor(private readonly call:(name:string,args:Record<string,unknown>)=>Promise<unknown>) {}
  update(status:ReturnType<VoicePort['status']>) { this.state={...status}; }
  status() { return {...this.state}; }
  async recognize(input:unknown) {
    if (!this.state.available) throw new Error(this.state.detail || '语音输入尚未配置');
    const result=await this.call('voice.recognize',{}) as {text?:unknown};
    if (typeof result.text !== 'string' || !result.text.trim()) throw new Error('未识别到清晰语音，请重试');
    return result.text.trim();
  }
  async speak(text:string,config:{language:'zh-CN';rate:0.9}) {
    if (!this.state.outputAvailable) throw new Error('当前语音宿主尚不支持朗读');
    await this.call('voice.speak',{text,...config});
  }
  cancel() { void this.call('voice.cancel',{}).catch(()=>{}); }
}
