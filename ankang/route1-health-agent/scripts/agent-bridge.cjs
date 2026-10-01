const readline = require('node:readline');
// stdout is reserved for one JSON response per request; diagnostics go to stderr.
console.log = console.error;
const { AgentRuntime } = require('../.bridge-build/runtime/index.js');
const runtime = new AgentRuntime();

async function main() {
  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    try {
      const request = JSON.parse(line);
      let result;
      switch (request.operation) {
        case 'open':
          result = await runtime.openSession({
            sessionId: request.sessionId,
            profile: request.profile,
            now: new Date(request.now),
          });
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
      process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
    } catch (error) {
      process.stdout.write(JSON.stringify({ ok: false, error: String(error) }) + '\n');
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
