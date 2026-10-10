const readline = require('node:readline');
// stdout is reserved for one JSON response per request; diagnostics go to stderr.
console.log = console.error;
const { AgentRuntime } = require('../.bridge-build/runtime/index.js');
const runtime = new AgentRuntime();
const { createRehabModel } = require('./rehab-model.cjs');
const { ProductService } = require('../.bridge-build/product/ProductService.js');
const { ProductLocalStore } = require('./product-local-store.cjs');
const { HttpVisionProvider } = require('../.bridge-build/adapters/HttpVisionProvider.js');
const { HealthKitDeviceAdapter } = require('../.bridge-build/adapters/HealthKitDeviceAdapter.js');
const { webhookFamilyDelivery } = require('../.bridge-build/adapters/FamilyNotificationDelivery.js');
const { HostVoicePort } = require('../.bridge-build/adapters/HostVoicePort.js');
let currentOwner = '';
const nativeVoice = process.env.ANKANG_NATIVE_VOICE === '1'
  ? new HostVoicePort((name, args) => readFromPython(currentOwner,{name,arguments:args})) : undefined;
const productRoot = process.argv[2];
const product = productRoot ? new ProductService(new ProductLocalStore(productRoot),
  owner => process.env.ANKANG_PRODUCT_DISABLE_MODEL === '1' ? undefined : createRehabModel(call => readFromPython(owner, call)),
  process.env.ANKANG_IMAGE_PROXY_URL ? new HttpVisionProvider({endpoint: process.env.ANKANG_IMAGE_PROXY_URL}) : undefined, {
    healthkit: process.env.ANKANG_HEALTHKIT_ENDPOINT ? new HealthKitDeviceAdapter(process.env.ANKANG_HEALTHKIT_ENDPOINT, process.env.HEALTHKIT_BRIDGE_TOKEN || '') : undefined,
    delivery: process.env.ANKANG_WEBHOOK_TOKEN ? webhookFamilyDelivery({provider:process.env.ANKANG_WEBHOOK_PROVIDER || 'custom',token:process.env.ANKANG_WEBHOOK_TOKEN,customUrl:process.env.ANKANG_WEBHOOK_URL}) : undefined,
    voice: nativeVoice,
  }, owner => ({read:() => readFromPython(owner,{name:'care.read',arguments:{}}),
    execute:(action,idempotencyKey,expiresAt) => readFromPython(owner,{name:'care.execute',arguments:{action,idempotencyKey,expiresAt}})})) : null;
const pending = new Map();
let sequence = 0;
const send = (value) => process.stdout.write(JSON.stringify(value) + '\n');
function readFromPython(sessionId, call) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('Rehab host read timed out'));
    }, call.name.startsWith('voice.') ? 135000 : 15000);
    pending.set(id, { resolve, reject, timer });
    send({ toolCall: { id, sessionId, ...call } });
  });
}

async function main() {
  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  let queue = Promise.resolve();
  async function handle(request) {
    try {
      let result;
      switch (request.operation) {
        case 'product':
          if (!product) throw new Error('Product data directory is required');
          currentOwner = request.sessionId;
          if (nativeVoice && request.voiceStatus) nativeVoice.update(request.voiceStatus);
          result = await product.request(request.productOperation, request.sessionId, request.payload || {}, new Date(request.now));
          break;
        case 'open':
          const rehabTools = request.rehabTools
            ? createRehabModel((call) => readFromPython(request.sessionId, call))
            : undefined;
          result = await runtime.openSession({
            sessionId: request.sessionId,
            profile: request.profile,
            now: new Date(request.now),
            rehabTools,
          });
          result.rehabToolsAvailable = Boolean(rehabTools);
          break;
        case 'process':
          result = await runtime.processTurn(request.sessionId, { text: request.text, now: new Date(request.now) });
          break;
        case 'close':
          await runtime.closeSession(request.sessionId);
          result = { sessionId: request.sessionId, closed: true };
          break;
        default:
          throw new Error('Expected operation: open, process or close');
      }
      send({ ok: true, result });
    } catch (error) {
      send({ ok: false, error: String(error) });
    }
  }
  // Tool replies must be consumed while a serialized Runtime turn is awaiting its host read.
  input.on('line', (line) => {
    let request;
    try {
      request = JSON.parse(line);
    } catch {
      send({ ok: false, error: 'Invalid JSON' });
      return;
    }
    if (request.operation === 'tool_result') {
      const wait = pending.get(request.id);
      if (!wait) return;
      pending.delete(request.id);
      clearTimeout(wait.timer);
      if (request.error) wait.reject(new Error(request.error));
      else wait.resolve(request.result);
    } else queue = queue.then(() => handle(request));
  });
  input.on('close', () => {
    for (const wait of pending.values()) {
      clearTimeout(wait.timer);
      wait.reject(new Error('Python host disconnected'));
    }
    pending.clear();
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
