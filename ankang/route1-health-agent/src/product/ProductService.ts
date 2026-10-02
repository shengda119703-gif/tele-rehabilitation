import { normalizeSyncEvents } from '../sync/protocol';
import { mainSpeechText, type ProductExtensions, type SyncPort } from './ExtensionPorts';
import { MeasurementInputAdapter } from '../adapters/MeasurementInputAdapter';
import { normalizeMeasurement } from '../adapters/HealthKitDeviceAdapter';
import { healthKitRevisionKey } from '../healthkit/autoSync';
/** Desktop product boundary. All domain decisions stay in the existing Ankang services. */
import { AgentRuntime, type SessionSnapshot } from '../runtime/session';
import type { PersistencePort, StoredSession } from '../runtime/ports';
import { scopeKey, type OwnerScope } from '../profile/OwnerScope';
import type { StoredProfile } from '../profile/ProfilePersistence';
import { MedicationService } from '../medication/MedicationService';
import { normalizeMedicationProfile, withMedicationRecords } from '../medication/medications';
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
  optional: ['image-recognition-proxy', 'voice', 'cross-device-sync', 'healthkit', 'external-notification', 'device-input'],
  retainedDisabled: ['home-twin', 'route2-spatial-modeling', '3dgs'],
  specialHardware: 'existing generic device and HealthKit bridges; no independent proprietary driver in upstream',
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
    private vision?: HealthVisionProvider, private extensions: ProductExtensions = {}) {}
  private syncs = new Map<string, {port:SyncPort; inbox:unknown[]; unsubscribe:() => void}>();
  private sync(owner:string) {
    if (!this.syncs.has(owner)) {
      const port = this.extensions.sync?.(owner);
      if (!port) throw new Error('Sync transport unavailable');
      const inbox:unknown[] = [];
      const unsubscribe = port.subscribe(e => {if (inbox.length < 200) inbox.push(e);});
      this.syncs.set(owner,{port,inbox,unsubscribe});
    }
    return this.syncs.get(owner)!;
  }
  private async ingest(owner:string, samples:unknown[], source:'device'|'healthkit'|'demo', now:Date) {
    if (!Array.isArray(samples) || samples.length > 10000) throw new Error('Invalid device batch');
    if (source === 'demo' && this.scope(owner).dataMode !== 'demo') throw new Error('Demo input requires demo profile');
    const measurements = samples.map((m,i) => normalizeMeasurement(m,i,source));
    await this.append(owner, measurements.map(measurementToEvent), now);
  }
  private async receiveSync(owner:string, raw:unknown, now:Date) {
    const {port} = this.sync(owner), scope = this.scope(owner), family = this.family(owner), state = family.readState();
    const e = raw as {type:string;payload:any;fromRole?:string;tabId?:string;at?:string};
    if (!e || typeof e.type !== 'string' || !e.payload || typeof e.payload !== 'object') return {applied:false,reason:'invalid-envelope'};
    let p = e.payload;
    if (e.type === 'family.link' && port.role === 'elder' && p.kind === 'request' && typeof p.code === 'string' && typeof p.requestId === 'string') {
      const link = family.confirmLinkRequest(p.code);
      if (!family.lastSave.ok) throw new Error('Family binding save failed');
      port.broadcast('family.link', link ? {kind:'accepted', requestId:p.requestId, link, consent:{sharing:state.familySharing === 'granted'?'granted':'denied',updatedAt:state.consentUpdatedAt}} : {kind:'rejected',requestId:p.requestId,reason:'code_mismatch'});
      return {applied:Boolean(link)};
    }
    if (port.via === 'peer' && state.familyLink?.status !== 'active') return {applied:false,reason:'unbound-peer'};
    if (['events.append','chat.append'].includes(e.type) && port.via === 'peer') return {applied:false,reason:'local-only-data'};
    if (e.type === 'family.consent') {
      const consentClock = p.sentAt ?? p.updatedAt;
      if (port.role !== 'family' || e.fromRole !== 'elder' || p.relationshipId !== state.familyLink?.id || !['granted','denied'].includes(p.sharing) || typeof p.updatedAt !== 'string' || !Number.isFinite(Date.parse(consentClock))) return {applied:false,reason:'invalid-consent'};
      const old = this.port.read<{relationshipId:string;at:string}>(this.key(owner,'sync-consent'));
      if (old && old.relationshipId === p.relationshipId && Date.parse(consentClock) <= Date.parse(old.at)) return {applied:false,reason:'stale-consent'};
      family.applyRemoteConsent(p,p.relationshipId);
      if (!family.lastSave.ok) throw new Error('Consent save failed');
      this.port.write(this.key(owner,'sync-consent'),{relationshipId:p.relationshipId,at:consentClock});
      await this.close(owner); return {applied:true};
    }
    if (e.type === 'medication.update' && p.ownerId === undefined) {
      if (p.mode !== scope.dataMode || p.familyId !== state.familyLink?.inviteCode || p.name !== this.profile(owner).profile.name || state.familyLink?.status !== 'active') return {applied:false,reason:'owner-mismatch'};
      p = {...p,ownerId:owner,dataMode:scope.dataMode};
    }
    if (e.type === 'signals.summary' && e.fromRole === 'elder' && (p.ownerId === undefined || (p.ownerId === owner && p.dataMode === scope.dataMode)) && typeof p.today === 'string' && [p.signalCount,p.gatedAlertCount].every(v => Number.isSafeInteger(v) && v >= 0)) {
      this.port.write(this.key(owner,'sync-summary'),p);return {applied:true};
    }

    if (p.ownerId !== owner || p.dataMode !== scope.dataMode) return {applied:false,reason:'owner-mismatch'};
    if (e.type === 'dispatch.acknowledge' || e.type === 'dispatch.append') {
      if (p.relationshipId !== state.familyLink?.id) return {applied:false,reason:'relationship-mismatch'};
      if (typeof p.findingId !== 'string') return {applied:false,reason:'invalid-record'};
      if (e.type === 'dispatch.append') {
        if (!Array.isArray(p.deliveries) || !['new','acknowledged'].includes(p.lifecycle) || typeof p.createdAt !== 'string' || typeof p.title !== 'string' || typeof p.message !== 'string' || typeof p.reason !== 'string' || !['alert','urgent'].includes(p.severity) || !['persistent','one_time'].includes(p.shareMode) || !['pending','accepted','sent','delivered','failed','unavailable'].includes(p.phase) || p.deliveries.some((d:any) => !d || !['in_app','browser_push','webhook_push'].includes(d.channel) || !['pending','accepted','sent','delivered','failed','unavailable'].includes(d.status) || typeof d.detail !== 'string' || typeof d.at !== 'string')) return {applied:false,reason:'invalid-record'};
        this.notification(owner).mergeRecord(p);
      } else this.notification(owner).acknowledge(p.findingId,now.toISOString());
      if (!this.notification(owner).lastSave.ok) throw new Error('Notification sync save failed');
      return {applied:true};
    }
    if (e.type === 'medication.update') {
      if (state.familySharing !== 'granted' || state.familyLink?.status !== 'active' || !Array.isArray(p.medicationRecords)) return {applied:false,reason:'medication-permission'};
      if (p.medicationRecords.length > 200 || p.medicationRecords.some((r:any) => !r || !['id','name','dose','purpose','times'].every(k => typeof r[k] === 'string') || !r.id || !r.name.trim() || !['active','stopped'].includes(r.status))) return {applied:false,reason:'invalid-medication'};
      const profile = this.profile(owner);
      this.port.write('profile:'+owner,{...profile,profile:withMedicationRecords(profile.profile,p.medicationRecords)});
      await this.close(owner);return {applied:true};
    }
    if (e.type === 'chat.append') {
      const m = p.message;
      if (!m || typeof m.id !== 'string' || !['elder','agent'].includes(m.role) || typeof m.text !== 'string' || typeof m.time !== 'string' || m.persisted === false || m.pending || ['private','no_record'].includes(parsePrivacyIntent(m.text))) return {applied:false,reason:'invalid-or-private-chat'};
      if (m.blocks !== undefined && (!Array.isArray(m.blocks) || m.blocks.some((b:any) => !b || !['main','receipt','privacy'].includes(b.kind) || typeof b.text !== 'string'))) return {applied:false,reason:'invalid-chat-blocks'};
      const snapshot = await this.session(owner,now);
      if (!snapshot.chat.some(v => v.id === m.id)) {
        await this.persistence(owner).save('',{revision:snapshot.revision+1,health:{events:snapshot.events,familyEvents:snapshot.familyEvents,chat:[...snapshot.chat.filter(v => v.persisted !== false),m]}});
        await this.close(owner);
      }
      return {applied:true};
    }
    if (e.type === 'events.append' && Array.isArray(p.events)) {
      let valid:HealthEvent[];
      try {valid=normalizeSyncEvents(p.events,scope.dataMode);} catch {return {applied:false,reason:'invalid-events'};}
      await this.append(owner,valid,now); return {applied:true};
    }
    if (e.type === 'chat.share' && e.fromRole === 'elder' && Array.isArray(p.sharedFindingIds) && Array.isArray(p.sharedFamilyEventIds) && [...p.sharedFindingIds,...p.sharedFamilyEventIds].every(v => typeof v === 'string')) {
      family.shareFindingIds(p.sharedFindingIds);family.shareFamilyEventIds(p.sharedFamilyEventIds);
      if (!family.lastSave.ok) throw new Error('Sharing sync save failed');
      return {applied:true};
    }
    return {applied:false,reason:'unsupported-or-private-message'};
  }
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
    if (operation === 'extensions.status') return {voice:this.extensions.voice?.status() ?? {available:false,phase:'unavailable'},
      devices:Object.keys(this.extensions.devices ?? {}), healthkit:Boolean(this.extensions.healthkit),
      notification:Boolean(this.extensions.delivery), syncSummary:this.port.read(this.key(owner,'sync-summary')), sync:this.syncs.get(owner)?.port.status() ?? {mode:'local-only', detail:'未连接外部通道',peerId:null}, externalAcceptance:'unverified'};
    if (operation === 'voice.input') {
      if (!this.extensions.voice) throw new Error('ASR adapter unavailable');
      const text = await this.extensions.voice.recognize(input);
      return this.request('chat',owner,{text},now);
    }
    if (operation === 'voice.output') {
      if (!this.extensions.voice) throw new Error('TTS adapter unavailable');
      const state = await this.session(owner,now), message = state.chat.find(m => m.id === input.id && m.role === 'agent');
      if (!message) throw new Error('Assistant message not found');
      await this.extensions.voice.speak(mainSpeechText(message),{language:'zh-CN',rate:0.9});return {accepted:true,delivered:false};
    }
    if (operation === 'voice.cancel') {this.extensions.voice?.cancel();return {cancelled:true};}
    if (operation === 'device.import') {
      if (input.ownerId !== owner) throw new Error('Device owner mismatch');
      if (!['device','demo'].includes(input.source)) throw new Error('Invalid device source');
      const adapter = new MeasurementInputAdapter(input.source,owner,input.measurements);
      await this.ingest(owner,await adapter.getMeasurements(owner,'0000-01-01','9999-12-31'),input.source,now);
      return this.snapshot(owner,now);
    }
    if (operation === 'device.pull' || operation === 'healthkit.import') {
      const adapter = operation === 'healthkit.import' ? this.extensions.healthkit : this.extensions.devices?.[input.adapter];
      if (!adapter) throw new Error('External device adapter unavailable');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(input.from) || !/^\d{4}-\d{2}-\d{2}$/.test(input.to) || input.from > input.to) throw new Error('Invalid date range');
      if (!['device','healthkit','demo'].includes(adapter.source)) throw new Error('Invalid device source');
      await this.ingest(owner,await adapter.getMeasurements(owner,input.from,input.to),adapter.source as 'device'|'healthkit'|'demo',now);
      if (operation === 'healthkit.import') this.port.write(this.key(owner,'healthkit-revision'),healthKitRevisionKey(this.extensions.healthkit?.lastDiagnostics) ?? null);
      return this.snapshot(owner,now);
    }
    if (operation === 'healthkit.diagnostics') {
      if (!this.extensions.healthkit) throw new Error('HealthKit external bridge unavailable; permission is requested by iOS companion');
      return {diagnostics:await this.extensions.healthkit.getDiagnostics(owner), lastAppliedKey:this.port.read(this.key(owner,'healthkit-revision')), permissionPlatform:'iOS companion'};
    }
    if (operation === 'sync.status' || operation === 'sync.start') return this.sync(owner).port.status();
    if (operation === 'sync.poll') {
      const sync = this.sync(owner), outcomes = [];
      while(sync.inbox.length) outcomes.push(await this.receiveSync(owner,sync.inbox.shift(),now));
      return {status:sync.port.status(),outcomes};
    }
    if (operation === 'sync.publish') {
      const sync = this.sync(owner), family = this.family(owner).readState();
      if (family.familyLink?.status !== 'active') throw new Error('Sync requires verified family relationship');
      if (sync.port.role !== 'elder') throw new Error('Only owner can publish consent and records');
      sync.port.broadcast('family.consent',{sharing:family.familySharing === 'granted'?'granted':'denied',updatedAt:now.toISOString(),relationshipId:family.familyLink.id});
      for (const record of this.notification(owner).read('family')) sync.port.broadcast('dispatch.append',record);
      return {accepted:true,delivered:false};
    }
    if (operation === 'sync.close') {const sync=this.syncs.get(owner);sync?.unsubscribe();sync?.port.close();this.syncs.delete(owner);return {closed:true};}
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
        const result = await family.bindFamily(String(input.code ?? ''), this.extensions.sync ? this.sync(owner).port : undefined);
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
    } else if (operation === 'media.import') {
      if (typeof input.batchId !== 'string' || !Number.isFinite(Date.parse(input.capturedAt)) || !Array.isArray(input.files) || input.files.length > 100) throw new Error('Invalid capture batch');
      if (input.files.some((f:any) => !f || typeof f.mediaType !== 'string' || !/^(image|video)\//.test(f.mediaType) || !Array.isArray(f.bytes) || f.bytes.length > 20*1024*1024 || f.bytes.some((b:any) => !Number.isInteger(b) || b < 0 || b > 255))) throw new Error('Invalid capture media');
      const archive = new ArchiveService(this.scope(owner), this.port.attachments, () => this.family(owner).readState());
      for (const file of input.files) await archive.save({...file,bytes:new Uint8Array(file.bytes)},input.capturedAt);
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
      await this.notification(owner).dispatch(state.findings, this.extensions.delivery ?? (async () => [{channel:'browser_push', status:'unavailable',
        detail:'本机台账已建立，外部家属通知渠道未启用'}]), now.toISOString());
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
      const sync=this.syncs.get(owner);sync?.unsubscribe();sync?.port.close();this.syncs.delete(owner);
      this.extensions.voice?.cancel();
      await this.port.attachments.clear(this.scope(owner));
      for (const kind of ['health','tasks','audit','notifications','family','healthkit-revision','sync-consent','sync-summary']) this.port.remove(this.key(owner, kind));
      this.families.get(owner)?.close(); this.families.delete(owner);
      this.notifications.get(owner)?.close(); this.notifications.delete(owner);
      this.pendingImages.delete(owner);
      // Profile/medications and the authoritative rehabilitation database are retained.
    } else throw new Error('Unknown product operation');
    return this.snapshot(owner, now);
  }
}
