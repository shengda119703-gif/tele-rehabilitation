const path = require('node:path');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
// Generated code must match the retained sources, including after a legacy cleanup.
const output = path.resolve(root, '.bridge-build');
if (path.dirname(output) !== root) throw new Error('Bridge output escaped the package directory');
fs.rmSync(output, { recursive: true, force: true });
const result = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), '-p', 'tsconfig.bridge.json'], {
  cwd: root,
  stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
fs.writeFileSync(path.join(root, '.bridge-build/package.json'), JSON.stringify({ type: 'commonjs' }));
