/** Desktop product boundary. All domain decisions stay in the existing Ankang services. */
import { AgentRuntime, type SessionSnapshot } from '../runtime/session';
import type { PersistencePort, StoredSession } from '../runtime/ports';
import { scopeKey, type OwnerScope } from '../profile/OwnerScope';
import type { StoredProfile } from '../profile/ProfilePersistence';
import { MedicationService } from '../medication/MedicationService';
import { normalizeMedicationProfile } from '../medication/medications';
import { FamilyService } from '../family/FamilyService';
import { durableFamilyState, type FamilyState } from '../family/FamilyPersistence';
import { ArchiveService, type AttachmentPort } from '../archive/ArchiveService';
import { NotificationService, type NotificationRecord } from '../notification/NotificationService';
import { readHealthHistory, metricTrend } from '../archive/healthHistory';
import { readPersonTwinProduct } from '../personTwin/readPersonTwinProduct';
import { familyStatus } from '../engine/dashboardStatus';
import { parsePrivacyIntent } from '../engine/privacy';
import { buildMedicationCareView } from '../engine/medicationCare';
import { appendHealthEvents, measurementToEvent, labResultToEvent, type HealthEvent } from '../pipeline/events';
import { METRICS, type CareTask, type ElderProfile, type MetricKey, type MedicationRecord } from '../types';
import { RealImageHealthParser } from '../adapters/RealImageHealthParser';
import type { HealthVisionProvider, ParsedHealthData } from '../adapters/ImageHealthParser';
import type { RehabToolPort } from '../runtime/rehabTools';

export interface ProductLocalPort {
  read<T>(key: string): T | null;
  write(key: string, value: unknown): void;
  remove(key: string): void;
  profiles(): StoredProfile[];
  attachments: AttachmentPort;
}
export const productCapabilities = {
  active: ['runtime', 'chat', 'self-report', 'profile', 'health-events', 'detection', 'person-twin',
    'medication', 'today-medication', 'care-tasks', 'emergency-contacts', 'sos-contact-info',
    'local-family-binding', 'sharing', 'family-facts', 'privacy', 'consent', 'correction',
    'archive', 'attachments', 'notification-ledger', 'family-summary', 'reports', 'trends',
    'timeline', 'local-lifecycle', 'image-input', 'image-confirmation'],
  optional: ['image-recognition-proxy'],
  retainedDisabled: ['voice', 'cross-device-sync', 'healthkit', 'home-twin', '3dgs', 'special-hardware'],
  video: 'archive-attachment; rehabilitation-camera-and-replay; no Ankang video-health-parser',
};

type ProductProfile = StoredProfile & { rehabGoal?: string; currentState?: string };
export class ProductService {
  private runtime = new AgentRuntime();
  private open = new Set<string>();
  private families = new Map<string, FamilyService>();
  private notifications = new Map<string, NotificationService>();
  private pendingImages = new Map<string, ParsedHealthData>();
  constructor(private port: ProductLocalPort, private rehab?: (owner: string) => RehabToolPort | undefined,
    private vision?: HealthVisionProvider) {}
  private profile(owner: string): ProductProfile {
    const value = this.port.read<ProductProfile>('profile:' + owner);
    if (!value || value.ownerId !== owner) throw new Error('请先建立当前用户健康档案');
    return value;
  }
  private scope(owner: string): OwnerScope {
    const p = this.profile(owner);
    return {ownerId: owner, dataMode: p.dataMode};
  }
  private key(owner: string, kind: string) { return kind + ':' + scopeKey(this.scope(owner)); }
  private family(owner: string): FamilyService {
    if (!this.families.has(owner)) {
      const scope = this.scope(owner);
      const loaded = this.port.read<FamilyState>(this.key(owner, 'family'));
      this.families.set(owner, new FamilyService(owner, scope.dataMode, {
        loadFamilyState: () => loaded,
        saveFamilyState: (_, state) => {
          this.port.write(this.key(owner, 'family'), durableFamilyState(state));
          return {ok: true, storage: 'persistent'};
        },
      }));
    }
    return this.families.get(owner)!;
  }
  private notification(owner: string) {
    // Reject a damaged durable ledger before the upstream optional-memory fallback can hide it.
    this.port.read<NotificationRecord[]>(this.key(owner, 'notifications'));
    if (!this.notifications.has(owner)) this.notifications.set(owner, new NotificationService(this.scope(owner),
      () => this.family(owner).readState(), {
        load: () => this.port.read<NotificationRecord[]>(this.key(owner, 'notifications')) ?? [],
        save: (_, records) => {
          this.port.write(this.key(owner, 'notifications'), records);
          return {ok: true, storage: 'persistent'};
        },
      }));
    return this.notifications.get(owner)!;
  }
  private persistence(owner: string): PersistencePort {
    return {
      load: async () => this.port.read<StoredSession>(this.key(owner, 'health')),
      save: async (_, value) => { this.port.write(this.key(owner, 'health'), value); return 'saved'; },
      clear: async () => {
        this.port.write(this.key(owner, 'health'), {revision: 0, health: {events: [], familyEvents: [], chat: []}});
        return 'saved';
      },
    };
  }
  private async close(owner: string) {
    if (this.open.delete(owner)) await this.runtime.closeSession(scopeKey(this.scope(owner)));
  }
  private async session(owner: string, now: Date): Promise<SessionSnapshot> {
    const scope = this.scope(owner), id = scopeKey(scope);
    if (this.open.has(owner) && this.runtime.readSnapshot(id).today !== this.day(now)) await this.close(owner);
    if (!this.open.has(owner)) {
      const profile = {...this.profile(owner).profile, familySharing: this.family(owner).readState().familySharing};
      await this.runtime.openSession({sessionId: id, profile, now, persistence: this.persistence(owner),
        rehabTools: this.rehab?.(owner)});
      this.open.add(owner);
      const history = this.port.read<CareTask[]>(this.key(owner, 'tasks')) ?? [];
      for (const task of this.runtime.readSnapshot(id).tasks) {
        const saved = history.find(t => t.id === task.id && t.dueDate === task.dueDate);
        if (saved) await this.runtime.updateTaskStatus(id, task.id, saved.status);
      }
    }
    return this.runtime.readSnapshot(id);
  }
  private day(now: Date) {
    return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  }
  private saveTasks(owner: string, tasks: CareTask[]) {
    const old = this.port.read<CareTask[]>(this.key(owner, 'tasks')) ?? [];
    this.port.write(this.key(owner, 'tasks'), [...old.filter(t => !tasks.some(n => n.id === t.id)), ...tasks]);
  }
  private async append(owner: string, events: HealthEvent[], now: Date) {
    const snapshot = await this.session(owner, now);
    await this.persistence(owner).save('', {revision: snapshot.revision + 1,
      health: {events: appendHealthEvents(snapshot.events, events), familyEvents: snapshot.familyEvents,
        chat: snapshot.chat.filter(m => m.persisted !== false)}});
    await this.close(owner);
  }
  async snapshot(owner: string, now: Date, viewer: 'self' | 'family' = 'self') {
    const scope = this.scope(owner), profile = this.profile(owner), state = await this.session(owner, now);
    const family = this.family(owner).readState();
    const projection = this.family(owner).project({ownerId: owner, findings: state.findings, tasks: state.tasks,
      familyEvents: state.familyEvents, measurements: state.healthData.measurements, selfEvents: state.events});
    const twin = readPersonTwinProduct({...scope, profile: profile.profile, events: state.events, tasks: state.tasks,
      familyEvents: state.familyEvents, family, today: state.today, asOf: now.toISOString()}, viewer);
    const archive = new ArchiveService(scope, this.port.attachments, () => this.family(owner).readState(), viewer);
    const notifications = this.notification(owner).read(viewer);
    if (viewer === 'family') return {
      ownerId: owner, canViewSharedDetail: projection.canViewSharedDetail, projection, twin, notifications,
      history: projection.canViewSharedDetail ? readHealthHistory(scope, profile.profile, state.events,
        state.familyEvents, state.findings, state.tasks, family, state.today, viewer) : null,
      attachments: projection.canViewSharedDetail ? await archive.list() : [],
      medication: buildMedicationCareView({medications: profile.profile.medications, tasks: projection.tasks,
        today: state.today, familySharing: projection.canViewSharedDetail ? 'granted' : 'denied', notifications: []}),
      status: familyStatus(this.notification(owner).viewNotifications(state.findings, state.today),
        notifications, projection.selfEvents.filter(e => e.timestamp.startsWith(state.today)).length),
    };
    const history = readHealthHistory(scope, profile.profile, state.events, state.familyEvents, state.findings,
      state.tasks, family, state.today);
    return {ownerId: owner, profile, state, twin, family, projection, history, notifications,
      attachments: await archive.list(),
      taskHistory: this.port.read<CareTask[]>(this.key(owner, 'tasks')) ?? [],
      audits: this.port.read<unknown[]>(this.key(owner, 'audit')) ?? [],
      trends: Object.fromEntries(Object.keys(METRICS).map(key => [key, metricTrend(history.records, key as MetricKey, state.today)])),
      capabilities: {...productCapabilities, imageRecognitionAvailable: Boolean(this.vision)},
      storage: 'persistent-local', modelAvailable: Boolean(this.rehab?.(owner))};
  }
  async request(operation: string, owner: string, input: Record<string, any>, now: Date): Promise<any> {
    if (!Number.isFinite(now.getTime())) throw new Error('Invalid clock');
    if (operation === 'profile.list') return this.port.profiles();
    if (operation === 'capabilities') return productCapabilities;
    if (operation === 'profile.save') {
      const p = input.profile as ElderProfile;
      if (!owner?.trim() || !p?.name?.trim() || !Number.isInteger(p.age) || p.age < 0 || p.age > 130
        || !Array.isArray(p.conditions) || !p.conditions.every(c => typeof c === 'string')
        || !Array.isArray(p.medications) || !p.medications.every(m => typeof m === 'string')) throw new Error('请核对称呼、年龄和健康档案');
      const old = this.port.read<ProductProfile>('profile:' + owner);
      const mode = old?.dataMode ?? input.dataMode ?? 'personal';
      if (!['personal','demo'].includes(mode)) throw new Error('Invalid data mode');
      if (old) await this.close(owner);
      // Consent is controlled by FamilyService, never silently granted by profile edits.
      const profile = normalizeMedicationProfile({...p, familySharing: old?.profile.familySharing ?? 'denied'});
      this.port.write('profile:' + owner, {version: 1, ownerId: owner, dataMode: mode, profile,
        rehabGoal: String(input.rehabGoal ?? old?.rehabGoal ?? ''), currentState: String(input.currentState ?? old?.currentState ?? '')});
      return this.snapshot(owner, now);
    }
    this.profile(owner);
    if (operation === 'snapshot') return this.snapshot(owner, now);
    if (operation === 'family.summary') return this.snapshot(owner, now, 'family');
    if (operation === 'chat') {
      if (typeof input.text !== 'string' || !input.text.trim() || input.text.length > 2000) throw new Error('请输入简短文字');
      await this.session(owner, now);
      const turn = await this.runtime.processTurn(scopeKey(this.scope(owner)), {text: input.text, now});
      const family = this.family(owner);
      family.shareFindingIds(turn.snapshot.sharedFindingIds);
      family.shareFamilyEventIds(turn.snapshot.sharedFamilyEventIds);
      this.saveTasks(owner, turn.tasks);
      // Existing upstream consent audit remains session-only; durable host log excludes no_record/private turns.
      if (turn.reply.persisted !== false && !['private','no_record'].includes(parsePrivacyIntent(input.text))) {
        const audit = this.port.read<unknown[]>(this.key(owner, 'audit')) ?? [];
        this.port.write(this.key(owner, 'audit'), [...audit, ...turn.appliedChanges.sharingAuditEntries].slice(-200));
      }
      if (turn.persistence.status === 'failed') throw new Error('健康记录未能保存到本机，请重试');
      return {turn, snapshot: await this.snapshot(owner, now)};
    }
    if (operation === 'medication.save' || operation === 'medication.status') {
      const medication = new MedicationService({loadProfile: async () => this.profile(owner),
        saveProfile: async (_, p) => {this.port.write('profile:' + owner, {...this.profile(owner), ...p}); return {ok: true, storage:'persistent'};}});
      const result = operation === 'medication.save' ? await medication.save(owner, input.record as MedicationRecord)
        : await medication.setStatus(owner, input.id, input.status);
      if (!result.ok) throw new Error(result.error);
      await this.close(owner);
    } else if (operation === 'task.status') {
      const state = await this.session(owner, now);
      if (!state.tasks.some(t => t.id === input.id) || !['pending','in_progress','completed','dismissed'].includes(input.status))
        throw new Error('任务或状态无效');
      const next = await this.runtime.updateTaskStatus(scopeKey(this.scope(owner)), input.id, input.status);
      this.saveTasks(owner, next.tasks);
    } else if (operation === 'health.record') {
      if (!Object.prototype.hasOwnProperty.call(METRICS,input.metric) || typeof input.value !== 'number' || !Number.isFinite(input.value)) throw new Error('指标或数值无效');
      const id = crypto.randomUUID(), metric = input.metric as MetricKey;
      await this.append(owner, [measurementToEvent({id, metric, value: input.value, unit: METRICS[metric].unit,
        timestamp: now.toISOString(), source:'manual', visibility: input.visibility === 'family_ok' ? 'family_ok':'private'})], now);
    } else if (operation.startsWith('family.')) {
      const family = this.family(owner);
      if (operation === 'family.invite') return {code: family.generateInvite(this.day(now)), family: family.readState()};
      if (operation === 'family.bind') {
        const result = await family.bindFamily(String(input.code ?? ''));
        if (!result.ok) throw new Error('邀请码不匹配；本机绑定需要先生成邀请码');
      } else if (operation === 'family.grant') {const result = family.grant(); if (!result.ok) throw new Error(result.error);}
      else if (operation === 'family.revoke') {const result = family.revoke(); if (!result.ok) throw new Error(result.error);}
      else if (operation === 'family.unbind') {const result = family.unbind(); if (!result.ok) throw new Error(result.error);}
      else throw new Error('Unknown family operation');
      if (!family.lastSave.ok) throw new Error(family.lastSave.error);
      const audits = this.port.read<unknown[]>(this.key(owner,'audit')) ?? [];
      this.port.write(this.key(owner,'audit'), [...audits, {action:operation, ownerId:owner,
        timestamp:now.toISOString(), relationshipId:family.readState().familyLink?.id ?? null,
        sharing:family.readState().familySharing, delivery:'not-sent'}].slice(-200));
      await this.close(owner);
    } else if (operation === 'archive.save') {
      const archive = new ArchiveService(this.scope(owner), this.port.attachments, () => this.family(owner).readState());
      await archive.save({...input, bytes: new Uint8Array(input.bytes)} as Parameters<ArchiveService['save']>[0], now.toISOString());
    } else if (operation === 'archive.read') {
      const archive = new ArchiveService(this.scope(owner), this.port.attachments, () => this.family(owner).readState());
      const entry = await archive.read(input.id);
      return {...entry, bytes: Array.from(entry.bytes)};
    } else if (operation === 'image.parse') {
      if (!this.vision) throw new Error('尚未配置图片识别服务；可先保存图片附件或手动记录数值');
      if (input.consent !== true) throw new Error('请先确认将此图片发送到已配置的识别服务');
      const blob = new Blob([new Uint8Array(input.bytes)], {type: input.mediaType});
      const parsed = await new RealImageHealthParser(this.vision).parse(blob, {capturedAt: now.toISOString(), kind: input.kind});
      this.pendingImages.set(owner, parsed);
      return parsed;
    } else if (operation === 'image.confirm') {
      const parsed = this.pendingImages.get(owner);
      if (!parsed || input.confirmed !== true) throw new Error('没有待确认的图片识别结果');
      await this.append(owner, [...parsed.measurements.map(measurementToEvent), ...parsed.labResults.map(labResultToEvent)], now);
      this.pendingImages.delete(owner);
    } else if (operation === 'notification.plan') {
      const state = await this.session(owner, now);
      await this.notification(owner).dispatch(state.findings, async () => [{channel:'browser_push', status:'unavailable',
        detail:'本机台账已建立，外部家属通知渠道未启用'}], now.toISOString());
      if (!this.notification(owner).lastSave.ok) throw new Error('通知台账保存失败');
    } else if (operation === 'notification.ack') {
      if (!this.notification(owner).read('family').some(n => n.findingId === input.id))
        throw new Error('当前授权范围内没有这条可确认通知');
      this.notification(owner).acknowledge(input.id, now.toISOString());
      if (!this.notification(owner).lastSave.ok) throw new Error('通知确认保存失败');
    } else if (operation === 'emergency.contacts') {
      const p = this.profile(owner).profile;
      return {emergency:'120', familyName:p.familyContact, familyPhone:p.familyPhone,
        communityDoctorPhone:p.communityDoctorPhone ?? '', automaticCall:false};
    } else if (operation === 'lifecycle.export') {
      return {version: 1, exportedAt: now.toISOString(), snapshot: await this.snapshot(owner, now),
        attachments: (await this.port.attachments.list(this.scope(owner))).map(a => ({...a, bytes:Array.from(a.bytes)}))};
    } else if (operation === 'lifecycle.clear') {
      if (input.confirmOwner !== owner) throw new Error('请明确确认当前用户编号');
      await this.close(owner);
      await this.port.attachments.clear(this.scope(owner));
      for (const kind of ['health','tasks','audit','notifications','family']) this.port.remove(this.key(owner, kind));
      this.families.get(owner)?.close(); this.families.delete(owner);
      this.notifications.get(owner)?.close(); this.notifications.delete(owner);
      this.pendingImages.delete(owner);
      // Profile/medications and the authoritative rehabilitation database are retained.
    } else throw new Error('Unknown product operation');
    return this.snapshot(owner, now);
  }
}
