// Read-only stock metadata check. Node 20 requires --experimental-websocket.
// Usage: node --experimental-websocket check-metadata.cjs HOST PROTOC PROTO_DIR
const {execFileSync} = require('node:child_process');
const [host, protoc, protoDir] = process.argv.slice(2);
if (!host || !protoc || !protoDir) throw Error('Expected HOST PROTOC PROTO_DIR');
const ws = new WebSocket(`ws://${host}:8765`);
ws.binaryType = 'arraybuffer';
let count = 0, largest = Buffer.alloc(0), first = 0, last = 0;
ws.addEventListener('message', ({data}) => {
  const payload = Buffer.from(data);
  count++;
  last = Date.now();
  if (!first) first = last;
  if (payload.length > largest.length) largest = payload;
});
ws.addEventListener('error', () => {
  console.error('Metadata WebSocket error');
  process.exit(1);
});
setTimeout(() => {
  console.log(JSON.stringify({messages: count, arrivalSpanMs: last-first,
    largestPayloadBytes: largest.length}));
  if (count) {
    console.log(execFileSync(protoc, ['--decode=hailo_analytics.Frame',
      `--proto_path=${protoDir}`, `${protoDir}/analytics_metadata.proto`],
      {input: largest, encoding:'utf8'}));
  }
  ws.close();
  process.exit(count ? 0 : 1);
}, 12000);
