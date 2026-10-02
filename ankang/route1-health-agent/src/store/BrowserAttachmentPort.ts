import { demoArchives } from '../data/demoArchives';
import {
  ArchiveService,
  scopeKey,
  type Attachment,
  type AttachmentPort,
  type OwnerScope,
  type Viewer,
} from '../archive/ArchiveService';
import type { FamilyService } from '../family/FamilyService';
const STORE = 'owned-files';
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open('ankang-health-attachments', 2);
    r.onupgradeneeded = () => {
      if (!r.result.objectStoreNames.contains(STORE)) r.result.createObjectStore(STORE, { keyPath: 'storageId' });
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
/** Original name-scoped files store is preserved, never silently assigned to a new owner. */
export const browserAttachmentPort: AttachmentPort = {
  async list(scope) {
    const db = await database();
    try {
      return await new Promise<Attachment[]>((resolve, reject) => {
        const request = db.transaction(STORE).objectStore(STORE).getAll();
        request.onsuccess = () =>
          resolve(
            (request.result as (Attachment & { storageId: string })[])
              .filter((a) => scopeKey(a) === scopeKey(scope))
              .map(({ storageId, ...entry }) => entry),
          );
        request.onerror = () => reject(request.error);
      });
    } finally {
      db.close();
    }
  },
  async put(scope, entry) {
    if (scopeKey(scope) !== scopeKey(entry)) throw new Error('Attachment owner mismatch');
    const db = await database();
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).put({ ...entry, storageId: `${scopeKey(scope)}:${entry.id}` });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  },
  async clear(scope) {
    const db = await database();
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        const r = tx.objectStore(STORE).openCursor();
        r.onsuccess = () => {
          const cursor = r.result;
          if (!cursor) return;
          if (scopeKey(cursor.value) === scopeKey(scope)) cursor.delete();
          cursor.continue();
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } finally {
      db.close();
    }
  },
};
export function createBrowserArchiveService(
  scope: OwnerScope,
  family: () => ReturnType<FamilyService['readState']>,
  viewer: Viewer = 'self',
) {
  return new ArchiveService(scope, browserAttachmentPort, family, viewer, async () =>
    Promise.all(
      demoArchives().map(async (a) => ({
        ...scope,
        id: a.id,
        name: a.name,
        category: a.category,
        date: a.date,
        fileName: a.file.name,
        mediaType: a.file.type,
        bytes: new Uint8Array(await a.file.arrayBuffer()),
        visibility: 'family_ok' as const,
      })),
    ),
  );
}
export function attachmentFile(entry: Attachment): File {
  return new File([entry.bytes.slice().buffer as ArrayBuffer], entry.fileName, { type: entry.mediaType });
}

/** Explicit existing "clear all local data" UI operation; not called by owner-scoped archive.clear(). */
export async function clearAllBrowserAttachments() {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('ankang-health-attachments');
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('请先关闭其他打开档案的标签页'));
  });
}
