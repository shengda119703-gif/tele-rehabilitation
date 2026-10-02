import { startListening } from '../adapters/BrowserVoiceAdapter';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './VoiceListeningDialog.css';

export function MicrophoneIcon() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <rect x="17" y="6" width="14" height="25" rx="7" />
      <path d="M11 24v2a13 13 0 0 0 26 0v-2M24 39v5M17 44h14" />
    </svg>
  );
}
export default function VoiceListeningDialog({
  onClose,
  onText,
}: {
  onClose: () => void;
  onText: (text: string) => void;
}) {
  const [phase, setPhase] = useState('starting');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const stop = useRef(() => {}),
    cancel = useRef(() => {});
  const closeButton = useRef<HTMLButtonElement>(null);
  const callback = useRef({ onText, onClose });
  callback.current = { onText, onClose };
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButton.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    const handle = startListening({phase:setPhase, transcript:setTranscript, error:setError,
      close:() => callback.current.onClose(), text:words => callback.current.onText(words)});
    stop.current = handle.stop; cancel.current = handle.cancel;
    return handle.dispose;
  }, [attempt]);
  return createPortal(
    <div
      className="voice-listening-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="voice-dialog-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape') cancel.current();
        if (event.key === 'Tab') {
          const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
          const first = buttons[0],
            last = buttons[buttons.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }
      }}
    >
      <section className={`voice-listening-sheet voice-phase-${phase}`}>
        <header className="voice-listening-header">
          <button ref={closeButton} onClick={() => cancel.current()} aria-label="返回并取消录音">
            ‹
          </button>
          <div>
            <h1 id="voice-dialog-title">AI 助手</h1>
            <p>有什么事，和我说说</p>
          </div>
          <span aria-hidden="true">···</span>
        </header>
        <div className="voice-listening-orbit">
          <i />
          <i />
          <i />
          <div className="voice-listening-mic">
            <MicrophoneIcon />
          </div>
        </div>
        <h2>
          {phase === 'listening'
            ? '正在听…'
            : phase === 'starting'
              ? '正在连接麦克风…'
              : phase === 'finishing'
                ? '正在识别…'
                : '暂时没能听到您'}
        </h2>
        <div className="voice-listening-wave" aria-hidden="true">
          {[8, 14, 10, 24, 36, 48, 30, 16, 12, 24, 16, 8].map((height, i) => (
            <span key={i} style={{ height, animationDelay: `${i * 0.09}s` }} />
          ))}
        </div>
        <p className="voice-listening-transcript" role="status">
          {phase === 'error'
            ? error
            : transcript || (phase === 'starting' ? '如弹出麦克风授权，请选择允许' : '请说出您想说的话')}
        </p>
        {phase !== 'error' && (
          <div className="voice-listening-examples">
            <p>您可以这样说：</p>
            {['我今天还有什么事情？', '帮我记录一下晚上吃药', '我最近的血压怎么样？', '我的常用药放在哪里？'].map(
              (example) => (
                <div key={example}>“{example}”</div>
              ),
            )}
          </div>
        )}
        <footer>
          {phase === 'error' ? (
            <button className="voice-listening-finish" onClick={() => setAttempt((n) => n + 1)}>
              重新尝试
            </button>
          ) : (
            phase === 'listening' && (
              <button className="voice-listening-finish" onClick={() => stop.current()}>
                说完了，发送
              </button>
            )
          )}
          <button className="voice-listening-cancel" onClick={() => cancel.current()}>
            <span aria-hidden="true">×</span>
            {phase === 'error' ? '返回输入文字' : '取消'}
          </button>
          <p>{phase === 'error' ? '没有发送任何语音内容' : '说完后会自动发送'}</p>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
