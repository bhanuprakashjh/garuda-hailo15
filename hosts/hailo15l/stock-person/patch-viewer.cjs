// Apply only to an isolated copy of the shipped web assets.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const dir = process.argv[2];
if (!dir) throw Error('Expected isolated web asset directory');
const bundle = path.join(dir, 'bundle.js');
const index = path.join(dir, 'index.html');
function change(file, before, after) {
  const old = fs.readFileSync(file, 'utf8');
  if (old.split(before).length !== 2) throw Error(`Expected exactly one anchor in ${file}`);
  const next = old.replace(before, after);
  const patch = `*** Begin Patch\n*** Update File: ${file}\n@@\n` +
    old.trimEnd().split('\n').map(s => '-' + s).join('\n') + '\n' +
    next.trimEnd().split('\n').map(s => '+' + s).join('\n') + '\n*** End Patch\n';
  execFileSync('apply_patch', [], {input: patch, stdio: ['pipe', 'pipe', 'pipe'], maxBuffer: 32*1024*1024});
}
change(bundle, 'null!=(u=t.classifications)&&u.length&&uS(e,t,a,c,i)',
  'globalThis.drawPersonTrackId(e,t,a,l,n,r)');
change(index, '<script defer="defer" src="bundle.js"></script>',
  '<script defer src="track-id-badge.js?v=1"></script><script defer src="person-selection.js?v=2"></script><script defer="defer" src="bundle.js?v=person-selection-1"></script>');
