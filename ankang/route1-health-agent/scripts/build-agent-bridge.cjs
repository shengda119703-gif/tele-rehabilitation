const path = require('node:path');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
// Generated code must match the retained sources, including after a legacy cleanup.
const output = path.resolve(root, '.bridge-build');
if (path.dirname(output) !== root) throw new Error('Bridge output escaped the package directory');
const staging = path.resolve(root, `.bridge-staging-${process.pid}`);
if (path.dirname(staging) !== root) throw new Error('Bridge staging escaped package');
const result = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), '-p', 'tsconfig.bridge.json', '--outDir', staging], {
  cwd: root,
  stdio: 'inherit',
  // tsc arguments below select a separate destination; the last good bridge stays usable.
});
if (result.error || result.status !== 0) {
  fs.rmSync(staging, { recursive: true, force: true });
  if (result.error) throw result.error;
  process.exit(result.status ?? 1);
}
fs.writeFileSync(path.join(staging, 'package.json'), JSON.stringify({ type: 'commonjs' }));
const previous = path.resolve(root, `.bridge-previous-${process.pid}`);
function renameWithRetry(from, to) {
  for (let attempt = 0; ; attempt++) {
    try { return fs.renameSync(from, to); }
    catch (error) {
      if (!['EPERM','EBUSY','EACCES'].includes(error.code) || attempt >= 5) throw error;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100 * (attempt + 1));
    }
  }
}
try {
  if (fs.existsSync(output)) renameWithRetry(output, previous);
  try { renameWithRetry(staging, output); }
  catch (error) { if (fs.existsSync(previous)) renameWithRetry(previous, output); throw error; }
} finally {
  fs.rmSync(staging, { recursive: true, force: true });
  // If rollback itself fails, retain the last good directory for recovery.
  if (fs.existsSync(path.join(output, 'runtime/index.js'))) fs.rmSync(previous, { recursive: true, force: true });
}
