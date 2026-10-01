import { useEffect, useState, type ReactNode } from 'react';
import {
  archiveCategories as categories,
  scopeKey,
  type ArchiveService,
  type AttachmentMetadata,
} from '../archive/ArchiveService';
import { attachmentFile } from '../store/BrowserAttachmentPort';
type Archive = AttachmentMetadata & { file: File };
export default function HealthArchivePage({
  children,
  onRecognize,
  demoMode = false,
  service,
}: {
  children: ReactNode;
  onRecognize?: (file: File) => void;
  demoMode?: boolean;
  service: ArchiveService;
}) {
  const [healthOpen, setHealthOpen] = useState(false);
  const scope = scopeKey(service.scope);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<'private' | 'family_ok'>('family_ok');
  const [revision, setRevision] = useState(0);
  const [items, setItems] = useState<AttachmentMetadata[]>([]);
  const [category, setCategory] = useState('全部');
  const [upload, setUpload] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [kind, setKind] = useState(categories[0]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Archive | null>(null);
  const [preview, setPreview] = useState('');
  useEffect(() => {
    let active = true;
    void service
      .list()
      .then((items) => {
        if (active) setItems(items);
      })
      .catch(() => {
        if (active) setError('本机附件读取失败或无权访问。');
      });
    return () => {
      active = false;
    };
  }, [service, revision]);
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('ankang-archive-updates');
    channel.onmessage = (e) => {
      if (e.data === scope) setRevision((r) => r + 1);
    };
    return () => channel.close();
  }, [scope]);
  useEffect(() => {
    if (!selected) return;
    const url = URL.createObjectURL(selected.file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [selected]);
  async function save() {
    if (!file || !name.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      await service.save({
        id: editingId ?? undefined,
        name,
        category: kind,
        fileName: file.name,
        mediaType: file.type,
        bytes: new Uint8Array(await file.arrayBuffer()),
        visibility,
      });
      setItems(await service.list());
      setEditingId(null);
      setVisibility('family_ok');
      if (typeof BroadcastChannel !== 'undefined') {
        const channel = new BroadcastChannel('ankang-archive-updates');
        channel.postMessage(scope);
        channel.close();
      }
      setUpload(false);
      setFile(null);
      setName('');
    } catch {
      setError('附件保存失败，可能存储空间不足。请保留原文件后重试。');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flow-page">
      <header className="page-title-block">
        <span className="page-kicker">医疗资料，集中整理</span>
        <h1>健康档案</h1>
        <p>
          {demoMode
            ? '演示档案包含 12 份模拟资料，可分类、预览和下载。非真实医疗文件。'
            : '附件目前仅保存在这台浏览器，不会自动上传云端。'}
        </p>
      </header>
      {error && <p role="alert">{error}</p>}
      {selected ? (
        <article className="card">
          <button className="btn-secondary" onClick={() => setSelected(null)}>
            返回档案
          </button>
          <h2>{selected.name}</h2>
          <button
            className="btn-secondary"
            onClick={() => {
              setEditingId(selected.id);
              setVisibility(selected.visibility);
              setName(selected.name);
              setKind(selected.category);
              setFile(selected.file);
              setSelected(null);
              setUpload(true);
            }}
          >
            编辑档案
          </button>
          <p>
            {selected.category} · {new Date(selected.date).toLocaleDateString()}
          </p>
          {selected.file.type.startsWith('image/') && (
            <img className="archive-preview" src={preview} alt={selected.name} />
          )}
          <a className="btn-secondary" href={preview} download={selected.file.name}>
            下载原文件
          </a>
        </article>
      ) : upload ? (
        <form
          className="card flow-form"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <h2>{editingId ? '编辑档案' : '上传新档案'}</h2>
          <label>
            拍照或选择图片
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setFile(f);
                  setName(f.name);
                }
              }}
            />
          </label>
          <label>
            从文件选择
            <input
              type="file"
              accept="image/*,.pdf"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setFile(f);
                  setName(f.name);
                }
              }}
            />
          </label>
          <label>
            档案名称
            <input required value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            类型
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <p>{file?.name || '尚未选择文件'}</p>
          <p className="muted">
            保存的是原始附件。识别与健康数据入档在下方“健康数据与图片识别”中单独确认，不会凭空生成报告内容。
          </p>
          <button className="btn-primary" disabled={!file || busy}>
            {busy ? '保存中…' : '保存档案'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setUpload(false);
              setEditingId(null);
              setVisibility('family_ok');
              setFile(null);
              setName('');
            }}
          >
            取消
          </button>
        </form>
      ) : (
        <>
          <div className="archive-grid">
            {categories.map((c, i) => (
              <button
                className={`card archive-category archive-color-${i}`}
                key={c}
                aria-pressed={category === c}
                onClick={() => setCategory(c)}
              >
                <span aria-hidden="true">▤</span>
                <strong>{c}</strong>
                <small>{items.filter((a) => a.category === c).length} 份</small>
              </button>
            ))}
          </div>
          <div className="section-head">
            <h2>{category === '全部' ? '最近上传' : category}</h2>
            <button className="btn-secondary" onClick={() => setCategory('全部')}>
              全部
            </button>
          </div>
          {items
            .filter((a) => category === '全部' || a.category === category)
            .reverse()
            .map((a) => (
              <button
                className="card medicine-row"
                key={a.id}
                onClick={() => {
                  void service
                    .read(a.id)
                    .then((entry) => setSelected({ ...a, file: attachmentFile(entry) }))
                    .catch(() => setError('附件读取失败或无权访问。'));
                }}
              >
                <strong>{a.name}</strong>
                <span>{a.category} ›</span>
              </button>
            ))}
          {items.length === 0 && <p className="muted">还没有档案，添加第一份资料吧。</p>}
          <button className="btn-primary flow-wide" onClick={() => setUpload(true)}>
            ＋ 上传新档案
          </button>
        </>
      )}
      {file?.type.startsWith('image/') && (
        <button
          type="button"
          className="btn-secondary"
          onClick={() => {
            setHealthOpen(true);
            onRecognize?.(file);
          }}
        >
          识别已选图片（确认后入档）
        </button>
      )}
      {selected?.file.type.startsWith('image/') && (
        <button
          type="button"
          className="btn-secondary"
          onClick={() => {
            setHealthOpen(true);
            onRecognize?.(selected.file);
          }}
        >
          识别这份图片档案
        </button>
      )}
      <details className="card archive-health" open={healthOpen} onToggle={(e) => setHealthOpen(e.currentTarget.open)}>
        <summary>健康数据与图片识别</summary>
        {children}
      </details>
    </section>
  );
}
