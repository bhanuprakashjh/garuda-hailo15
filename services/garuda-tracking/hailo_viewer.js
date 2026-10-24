'use strict';
// Keep stock video and its overlay together; do not introduce another box renderer.
const stock = new URL(location.href); stock.port = '80'; stock.pathname = '/'; stock.search = ''; stock.hash = '';
document.getElementById('video').src = stock.href;
document.getElementById('standalone').href = stock.href;
const status = document.getElementById('status'), tracks = document.getElementById('tracks');
let lastSuccess = 0, current = null, commandPending = false;
const selection = document.getElementById('selection'), notice = document.getElementById('notice');
const rows = new Map();
function notifyVideo(value) {
  document.getElementById('video').contentWindow.postMessage({type:'garuda-selection',selection:value},stock.origin);
}
function clear(message) {
  renderDiagnostics(null);
  status.textContent = message; status.dataset.live = 'false';
  tracks.textContent = 'No current project tracks.';
  document.getElementById('age').textContent = '—';
  rows.clear(); current = null;
  selection.textContent = 'Selection unavailable · stale input'; selection.dataset.state='lost';
  notifyVideo({state:'lost',id:null});
}
function render(snapshot) {
  current = snapshot;
  renderDiagnostics(snapshot);
  const label = snapshot.target_label || 'person';
  const title = label === 'all' ? 'Garuda / YOLO11 diagnostics' : label === 'cell phone' ? 'Garuda / YOLO11 phone tracking' : 'Garuda / Hailo person tracking';
  document.querySelector('h1').textContent = title; document.title = title;
  const chosen = snapshot.selection || {state:'none',id:null};
  selection.textContent = chosen.state === 'none' ? 'No track selected' : `${chosen.state === 'lost' ? 'Lost' : 'Selected'} · ID ${chosen.id}`;
  selection.dataset.state = chosen.state;
  notifyVideo(chosen);
  status.textContent = snapshot.metadata_live ? 'Live · Hailo input' : snapshot.connection;
  status.dataset.live = String(snapshot.metadata_live);
  document.getElementById('age').textContent = snapshot.arrival_age_ms == null ? '—' : `${Math.round(snapshot.arrival_age_ms)} ms`;
  document.getElementById('session').textContent = snapshot.source_session.slice(0, 8);
  if (!rows.size) tracks.replaceChildren();
  const present = new Set(snapshot.tracks.map(t=>t.id));
  for (const [id,row] of rows) if (!present.has(id)) {row.remove();rows.delete(id);}
  for (const track of snapshot.tracks) {
    let row = rows.get(track.id);
    if (!row) {
      row = document.createElement('button'); row.type='button'; row.className = 'track';
      const id = document.createElement('div'); id.className = 'id'; id.textContent = `ID ${track.id}`;
      const detail = document.createElement('div'); detail.className = 'detail'; row.append(id,detail);
      row.addEventListener('click',()=>selectPerson(track.id));rows.set(track.id,row);tracks.append(row);
    }
    row.setAttribute('aria-label',`Select ${track.label} ID ${track.id}`);
    row.setAttribute('aria-pressed',String(chosen.state==='selected' && chosen.id===track.id));
    const detail=row.querySelector('.detail');
    detail.textContent = `${track.label} · ${(track.conf*100).toFixed(0)}% confidence`;
  }
  if (!snapshot.tracks.length) tracks.textContent = snapshot.metadata_live ? 'No confirmed tracks in this frame.' : 'No current project tracks.';
}
function renderDiagnostics(snapshot) {
  const canvas=document.getElementById('rawCanvas'), ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const output=document.getElementById('diagnostics'), list=document.getElementById('rawList');
  list.replaceChildren();
  const d=snapshot?.last_detection, age=snapshot?.last_detection_arrival_age_ms;
  if (!snapshot?.metadata_live || !d || age==null || age>300) {
    output.textContent=snapshot?.diagnostic_error || 'No recent raw detector sample.'; return;
  }
  const phone=d.raw.filter(x=>x.label==='cell phone');
  output.textContent=`Latest detector frame: ${d.raw.length} boxes, ${phone.length} phones · received ${Math.round(age)} ms ago. ${d.aligned?'Source timestamps match.':'Warning: video/AI timestamps differ.'}`;
  const sx=canvas.width/snapshot.frame.width, sy=canvas.height/snapshot.frame.height;
  ctx.strokeStyle='#ffad55';ctx.fillStyle='#ffad55';ctx.font='14px sans-serif';
  for(const b of d.raw) {
    ctx.strokeRect(b.x*sx,b.y*sy,b.w*sx,b.h*sy);
    ctx.fillText(b.label,Math.max(0,b.x*sx),Math.max(14,b.y*sy));
  }
  for(const b of [...d.raw].sort((a,b)=>b.conf-a.conf).slice(0,10)) {
    const row=document.createElement('p');row.textContent=`${b.label}: ${(b.conf*100).toFixed(0)}% (before tracking)`;list.append(row);
  }
}
async function command(path, payload) {
  if (commandPending) return;
  commandPending=true; notice.textContent='';
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),1500);
  try {
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
    const result=await response.json();
    if (!response.ok || !result.ok) throw Error(result.error || 'Selection rejected');
    render(result.snapshot);
  } catch(error) {notice.textContent=error.message;}
  finally {clearTimeout(timeout);commandPending=false;}
}
function selectPerson(id) {
  if (!current || !current.metadata_live || performance.now()-lastSuccess>300) {notice.textContent='Wait for current tracks.';return;}
  command('/api/select',{id,source_session:current.source_session,sequence:current.sequence});
}
document.getElementById('clearSelection').addEventListener('click',()=>command('/api/unlock',{}));
window.addEventListener('message',event=>{
  if(event.origin!==stock.origin || event.source!==document.getElementById('video').contentWindow) return;
  if(event.data?.type==='garuda-person-click' && Number.isInteger(event.data.id)) selectPerson(event.data.id);
  if(event.data?.type==='garuda-person-ambiguous') notice.textContent='Boxes overlap. Click an ID badge or track card.';
});
async function poll() {
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 800);
  try {
    const response = await fetch('/api/snapshot', {cache:'no-store',signal:controller.signal});
    if (!response.ok) throw Error('Adapter unavailable');
    render(await response.json()); lastSuccess = performance.now();
  } catch (_) { clear('Project input disconnected'); }
  finally { clearTimeout(timeout); setTimeout(poll,100); }
}
setInterval(() => {if (performance.now()-lastSuccess > 500) clear('Project input stale');},100);
poll();
