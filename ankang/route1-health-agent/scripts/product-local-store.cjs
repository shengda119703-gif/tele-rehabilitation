// Desktop adapter for existing business ports. No domain rules or browser storage here.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
// Windows sync/antivirus readers may briefly prevent replacement of a file.
// Retry only sharing/permission errors, never a full disk or invalid data.
function withFileRetry(operation) {
  const delays = [25, 50, 100, 200, 400];
  const waiter = new Int32Array(new SharedArrayBuffer(4));
  for (let attempt = 0; ; attempt++) {
    try { return operation(); }
    catch (error) {
      if (!['EPERM', 'EACCES', 'EBUSY'].includes(error.code) || attempt >= delays.length) throw error;
      Atomics.wait(waiter, 0, 0, delays[attempt]);
    }
  }
}
class ProductLocalStore {
  constructor(root) {
    this.root = path.resolve(root);
    fs.mkdirSync(this.root, { recursive: true, mode: 0o700 });
    this.attachments = {
      list: async scope => (this.read(this.attachmentKey(scope)) || []).map(entry => {
        const {content, ...metadata} = entry;
        return {...metadata, bytes: new Uint8Array(Buffer.from(content, 'base64'))};
      }),
      put: async (scope, entry) => {
        if (scope.ownerId !== entry.ownerId || scope.dataMode !== entry.dataMode) throw new Error('Attachment scope mismatch');
        const key = this.attachmentKey(scope), previous = this.read(key) || [];
        const {bytes, ...metadata} = entry;
        this.write(key, [...previous.filter(a => a.id !== entry.id), {...metadata, content: Buffer.from(bytes).toString('base64')}]);
      },
      clear: async scope => this.remove(this.attachmentKey(scope)),
    };
  }
  attachmentKey(scope) { return 'attachments:' + scope.dataMode + ':' + encodeURIComponent(scope.ownerId); }
  file(key) {
    const folder = key.startsWith('profile:') ? 'profiles' : 'records';
    return path.join(this.root, folder, crypto.createHash('sha256').update(key).digest('hex') + '.json');
  }
  read(key) {
    const file = this.file(key);
    if (!fs.existsSync(file)) return null;
    const envelope = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (envelope.key !== key || envelope.version !== 1) throw new Error('Product storage integrity failure');
    return envelope.value;
  }
  write(key, value) {
    const file = this.file(key);
    fs.mkdirSync(path.dirname(file), {recursive:true, mode:0o700});
    const temporary = file + '.' + crypto.randomUUID() + '.tmp';
    try {
      fs.writeFileSync(temporary, JSON.stringify({version:1, key, value}), {mode:0o600, flag:'wx'});
      if (fs.existsSync(file)) withFileRetry(() => fs.copyFileSync(file, file + '.bak'));
      withFileRetry(() => fs.renameSync(temporary, file));
    } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
  }
  profiles() {
    const folder = path.join(this.root, 'profiles');
    if (!fs.existsSync(folder)) return [];
    return fs.readdirSync(folder).filter(f => f.endsWith('.json')).map(f => {
      const envelope = JSON.parse(fs.readFileSync(path.join(folder, f), 'utf8'));
      const p = envelope.value;
      if (!p || envelope.version !== 1 || envelope.key !== 'profile:' + p.ownerId) throw new Error('Invalid local profile');
      return p;
    });
  }
  remove(key) {
    // Only derived, hashed files under this adapter's directory; never recursive.
    const file = this.file(key);
    for (const target of [file, file + '.bak']) if (fs.existsSync(target)) fs.unlinkSync(target);
  }
}
module.exports = {ProductLocalStore};
