import { scopeKey, type OwnerScope } from '../profile/OwnerScope';
export { scopeKey, type OwnerScope } from '../profile/OwnerScope';
import type { FamilyState } from '../family/FamilyPersistence';
import { buildFamilyProjection } from '../family/projection';
export type Viewer = 'self' | 'family';
export function requireFamilyAccess(scope: OwnerScope, viewer: Viewer, family: FamilyState): void {
  if (family.ownerId !== scope.ownerId || family.dataMode !== scope.dataMode)
    throw new Error('Family owner/mode mismatch');
  if (
    viewer === 'family' &&
    !buildFamilyProjection(family, {
      ownerId: scope.ownerId,
      findings: [],
      tasks: [],
      familyEvents: [],
      measurements: [],
    }).canViewSharedDetail
  )
    throw new Error('Family access not granted');
}
export const archiveCategories = ['体检报告', '就诊记录', '检验检查', '影像资料', '病历资料', '其他资料'];
export interface Attachment extends OwnerScope {
  id: string;
  name: string;
  category: string;
  date: string;
  fileName: string;
  mediaType: string;
  bytes: Uint8Array;
  visibility: 'private' | 'family_ok';
  trashedAt?: string;
}
export type AttachmentMetadata = Omit<Attachment, 'bytes'> & { size: number };
export interface AttachmentPort {
  list(scope: OwnerScope): Promise<Attachment[]>;
  put(scope: OwnerScope, attachment: Attachment): Promise<void>;
  clear(scope: OwnerScope): Promise<void>;
  setTrash?(scope: OwnerScope, id: string, at: string | null): Promise<void>;
}
export class InMemoryAttachmentPort implements AttachmentPort {
  private values = new Map<string, Attachment[]>();
  async list(scope: OwnerScope) {
    return structuredClone(this.values.get(scopeKey(scope)) ?? []);
  }
  async put(scope: OwnerScope, entry: Attachment) {
    if (scopeKey(scope) !== scopeKey(entry)) throw new Error('Attachment owner mismatch');
    this.values.set(scopeKey(scope), [
      ...(await this.list(scope)).filter((a) => a.id !== entry.id),
      structuredClone(entry),
    ]);
  }
  async clear(scope: OwnerScope) {
    this.values.delete(scopeKey(scope));
  }
}
/** Files remain separate from HealthEvent. No DOM/File/URL/IndexedDB in this service. */
export class ArchiveService {
  constructor(
    readonly scope: OwnerScope,
    private port: AttachmentPort,
    private family: () => FamilyState,
    readonly viewer: Viewer = 'self',
    private demo: () => Promise<Attachment[]> = async () => [],
  ) {
    scopeKey(scope);
  }
  private check() {
    requireFamilyAccess(this.scope, this.viewer, this.family());
  }
  private async entries() {
    this.check();
    const saved = (await this.port.list(this.scope)).filter((a) => scopeKey(a) === scopeKey(this.scope));
    const seeds = this.scope.dataMode === 'demo' ? await this.demo() : [];
    this.check();
    return [
      ...seeds.filter((a) => scopeKey(a) === scopeKey(this.scope) && !saved.some((s) => s.id === a.id)),
      ...saved,
    ].filter((a) => !a.trashedAt && (this.viewer === 'self' || a.visibility !== 'private'));
  }
  async trashList(): Promise<AttachmentMetadata[]> {
    this.check();
    if (this.viewer !== 'self') throw new Error('Only owner can view archive trash');
    return (await this.port.list(this.scope)).filter(a => scopeKey(a) === scopeKey(this.scope) && a.trashedAt)
      .map(({bytes,...metadata}) => ({...metadata,size:bytes.byteLength}));
  }
  async setTrash(id: string, at: string | null) {
    this.check();
    if (this.viewer !== 'self' || !this.port.setTrash) throw new Error('Archive trash unavailable');
    await this.port.setTrash(this.scope,id,at);
    this.check();
  }
  async list(): Promise<AttachmentMetadata[]> {
    return (await this.entries()).map(({ bytes, ...metadata }) => ({ ...metadata, size: bytes.byteLength }));
  }
  async read(id: string) {
    const entry = (await this.entries()).find((a) => a.id === id);
    if (!entry) throw new Error('Attachment not found');
    return structuredClone(entry);
  }
  async save(
    input: Omit<Attachment, 'ownerId' | 'dataMode' | 'id' | 'date'> & { id?: string },
    now = new Date().toISOString(),
  ) {
    this.check();
    if (!input.name.trim() || !archiveCategories.includes(input.category)) throw new Error('请填写档案名称和类型');
    if (input.id) await this.read(input.id);
    this.check();
    const entry: Attachment = {
      ...input,
      ...this.scope,
      id: input.id ?? crypto.randomUUID(),
      name: input.name.trim(),
      date: now,
    };
    await this.port.put(this.scope, entry);
    this.check();
    return structuredClone(entry);
  }
  /** Existing clear-local-data operation only; no new per-file delete product flow. */
  async clear() {
    this.check();
    if (this.viewer !== 'self') throw new Error('Only owner can clear archives');
    await this.port.clear(this.scope);
  }
}
