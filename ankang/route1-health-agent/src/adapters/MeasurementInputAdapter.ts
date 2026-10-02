import type { DeviceAdapter } from './DeviceAdapter';
import type { DataSource } from '../types';
import { normalizeMeasurement } from './HealthKitDeviceAdapter';
/** Existing health-device schema; caller supplies an explicit owner, never inferred identity. */
export class MeasurementInputAdapter implements DeviceAdapter {
  constructor(readonly source: DataSource, private ownerId:string, private samples:unknown[]) {}
  async getMeasurements(userId:string, from:string, to:string) {
    if (userId !== this.ownerId) throw new Error('Device owner mismatch');
    return this.samples.map((sample,index) => normalizeMeasurement(sample,index,this.source))
      .filter(m => m.timestamp.slice(0,10) >= from && m.timestamp.slice(0,10) <= to);
  }
}
