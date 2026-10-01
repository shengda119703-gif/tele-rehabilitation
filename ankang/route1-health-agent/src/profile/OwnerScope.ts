import type { DataMode } from './ProfilePersistence';
/** Same stable owner used by profile, medication and family; mode is a data partition, not an identity. */
export interface OwnerScope {
  ownerId: string;
  dataMode: DataMode;
}
export function scopeKey(scope: OwnerScope): string {
  if (!scope.ownerId.trim()) throw new Error('ownerId required');
  return `${scope.dataMode}:${encodeURIComponent(scope.ownerId)}`;
}
