'use strict';

const fmt = (value, digits = 0) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const commandText = p => p ? 'N ' + fmt(p.vn, 2) + ' · E ' + fmt(p.ve, 2) + ' m/s · yaw ' + fmt(p.yaw_rate, 3) + ' rad/s' : 'No message';

// Presentation never grants a control permit. Deadlines continue ageing between
// HTTP responses; a retained identity and a historic wire packet are not motion.
function presentation(s, elapsed = 0, connected = true) {
    connected = connected && !!s && elapsed >= 0 && elapsed < 750;
    const lock = s?.output?.lock || {};
    const retained = !!(lock.id && (lock.identity_retained || lock.identity_locked));
    const age = Number.isFinite(s?.receiver_age_ms) ? s.receiver_age_ms + elapsed : Infinity;
    const fresh = connected && retained && lock.observation_valid && lock.control_valid
        && s.flight === 'Hover / offboard' && s.follow_enabled && s.control_request_fresh
        && Number.isFinite(s.control_request_remaining_ms) && s.control_request_remaining_ms > elapsed
        && age >= 0 && age < 200;
    const flight = s?.flight || 'Unknown';
    const hover = connected && flight === 'Hover / offboard';
    let title = 'Select a target', help = 'Click a detection in the image or choose a target button below.', tone = 'neutral';
    if (!connected) {
        title = 'Connection lost — controls unavailable'; help = 'Displayed frames and command values may be old. Reconnect to the local demo.'; tone = 'warn';
    } else if (flight === 'Landing') {
        title = 'Landing the simulated drone'; help = 'Follow is off. Wait for PX4 to confirm disarm.';
    } else if (flight === 'Taking off') {
        title = 'Taking off in simulation'; help = 'Wait for confirmed hover before enabling follow.';
    } else if (!retained) {
        if (lock.id) { title = 'Target identity expired'; help = 'Select the target again. An old ID does not authorize movement.'; tone = 'warn'; }
    } else if (!hover) {
        title = 'Target selected · simulator disarmed'; help = 'Take off in simulation, then enable follow. Selecting a target alone does not move the drone.';
    } else if (!s.follow_enabled) {
        title = 'Hovering · follow is off'; help = 'Enable follow when ready. Hold keeps the simulated drone hovering.';
    } else if (lock.state === 'ambiguous' || lock.state === 'reacquiring' || !lock.observation_valid) {
        title = 'Follow enabled · waiting for the target'; help = 'The identity is retained, but the current observation is not verified. Motion requests stay on HOLD.'; tone = 'warn';
    } else if (!fresh) {
        title = 'Follow enabled · waiting for fresh evidence'; help = 'The current observation or request has expired or failed a control gate. It cannot drive movement.'; tone = 'warn';
    } else if (s.mavros?.last_wire && !s.mavros.last_wire.allowed) {
        title = 'Follow enabled · relay rejected a command'; help = 'The PC requested motion, but the last packet failed the independent relay checks. See command status below.'; tone = 'warn';
    } else {
        title = 'Follow enabled · fresh motion requested'; help = 'Check the last command sent and the actual Gazebo response. A fresh request alone is not proof of delivery.'; tone = 'good';
    }
    return {connected, retained, age, fresh, flight, hover, title, help, tone,
        canTakeoff: connected && ['Disarmed', 'Landed / disarmed'].includes(flight),
        canFollow: hover && retained && !s.follow_enabled,
        canLand: connected && ['Hover / offboard', 'Taking off', 'Landing'].includes(flight)};
}

// Heading dial: a top-down drone glyph rotated to the vehicle's actual yaw (PX4 heading,
// 0° = north, clockwise positive) and a ghost arrow at the requested yaw. Pure so it can be
// tested; the DOM only applies the returned transforms.
function headingDial(headingDeg, requestedDeg, connected = true) {
    const actual = connected && Number.isFinite(headingDeg);
    const requested = actual && Number.isFinite(requestedDeg);
    return {
        actualTransform: actual ? 'rotate(' + headingDeg.toFixed(1) + 'deg)' : 'rotate(0deg)',
        requestedTransform: requested ? 'rotate(' + requestedDeg.toFixed(1) + 'deg)' : 'rotate(0deg)',
        actualHidden: !actual, requestedHidden: !requested,
        label: actual ? 'Drone heading ' + headingDeg.toFixed(1) + '°' + (requested ? ', requested ' + requestedDeg.toFixed(1) + '°' : '') : 'Drone heading unavailable'
    };
}
// Link log: the relay serves the last entries with monotonic ids; only unseen ids are appended.
function newLinkEntries(entries, lastId) {
    return (Array.isArray(entries) ? entries : []).filter(e => e && Number.isInteger(e.id) && e.id > lastId).sort((a, b) => a.id - b.id);
}
// What the board is running on these pixels: model hash, schedule and this frame's crop state.
// Never guesses: without a staged profile in the state it says so, and the live desk camera
// (its profile is chosen on the board) is named as such.
function profileText(s, connected = true) {
  if (!connected) return 'Board profile unknown while disconnected.';
  const p = s?.board_profile, b = s?.board_schedule;
  if (!p) return s?.pixel_source?.startsWith('Physical') ? 'Desk node profile · chosen on the board (fresh_tracking_ctl.sh)' : 'Board profile not reported.';
  const aerial = /aerial/.test(p.path || '');
  const model = (aerial ? 'Aerial fine-tune ' : 'Controlled COCO ') + (p.hef_sha256 || '').slice(0, 8);
  const schedule = p.schedule === 'fullview' ? 'single view' : p.schedule === 'fullview_roi' ? 'single view + ROI'
    : 'tiles while searching · handover ' + p.follow_local_gap_ms + ' / ' + p.follow_global_period_ms + ' ms';
  const frame = !b ? '' : ' · this frame: ' + (b.global_pass ? 'tiles' : 'single') + (b.roi ? ' + ROI' : '') + (b.roi_reason ? ' (' + b.roi_reason + ')' : '');
  return model + ' · ' + schedule + ' · cap ' + p.max_detections + frame;
}
// How old the displayed frame may be for a click or an ID button to be sent. Live and simulated
// sources: 500 ms, so a selection always refers to a picture the operator is still looking at.
// Recorded replay: the displayed frame is transport-bound (300–700 ms at the PC even while the
// board is current), so the window is 2 s; the board still applies its own freshness rule to
// the selection, and the frame sequence travels with the click either way.
function selectionWindowMs(s) {
  return s?.pixel_source?.startsWith('Recorded') ? 2000 : 500;
}
// Repeat a refused selection only for refusals the board resolves by itself within a moment
// (the descriptor it is now computing for that person; a track observed just before), for at
// most 2 s and 5 tries after the operator's own request. Never for "no object there" or any
// other refusal: those need the operator to choose again.
function shouldRetrySelection(error, last, now) {
  if (!last || !error) return false;
  if (!/descriptor|freshly observed/i.test(error)) return false;
  return last.retries < 5 && now - last.at < 2000;
}
// Double-click follow: 'send' once the identity is retained and the aircraft can follow, 'wait'
// meanwhile, 'expired' after the window (the operator double-clicked something that never verified).
function followDue(view, pendingAt, now, windowMs = 6000) {
    if (pendingAt === null || pendingAt === undefined) return 'idle';
    if (now - pendingAt > windowMs) return 'expired';
    return view && view.connected && view.retained && view.canFollow ? 'send' : 'wait';
}
// Pause is a recorded-clip control only: hidden on live and simulated sources, and it flips to
// "Resume" while the clip is held so one button carries the state the backend reports.
function pauseButton(s, connected) {
    const recorded = !!s?.pixel_source?.startsWith('Recorded');
    return {hidden: !recorded, disabled: !connected || !recorded, action: s?.replay_paused ? 'resume' : 'pause',
            label: s?.replay_paused ? 'Resume clip' : 'Pause clip'};
}
if (typeof module !== 'undefined') module.exports = {presentation, fmt, commandText, headingDial, newLinkEntries, profileText, selectionWindowMs, shouldRetrySelection, pauseButton, followDue};

if (typeof document !== 'undefined') {
    const $ = id => document.getElementById(id);
    let lastLinkId = 0, linkCounts = null, linkCountsAt = 0, linkRate = 0;
    function appendLinkLog(m, connected) {
        const box = $('link-log');
        const fresh = newLinkEntries(m?.link_log, lastLinkId);
        if (fresh.length) {
            if (lastLinkId === 0) box.textContent = '';
            const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
            for (const e of fresh) {
                const line = document.createElement('span');
                line.className = 'l ' + e.lane + ' ' + (e.tone || 'info');
                const t = document.createElement('time'); t.textContent = e.time || '';
                const lane = document.createElement('span'); lane.className = 'lane'; lane.textContent = e.lane;
                line.append(t, lane, document.createTextNode(e.text || ''));
                box.append(line);
                lastLinkId = e.id;
            }
            while (box.childElementCount > 400) box.firstElementChild.remove();
            if (atBottom) box.scrollTop = box.scrollHeight;
        }
        const now = performance.now();
        if (m && now - linkCountsAt >= 1000) {
            const total = (m.motion_forwarded || 0) + (m.motion_rejected || 0);
            if (linkCounts !== null) linkRate = (total - linkCounts) * 1000 / (now - linkCountsAt);
            linkCounts = total; linkCountsAt = now;
        }
        $('link-stats').textContent = !connected ? 'Disconnected' : !m ? 'Waiting for the relay'
            : `${fmt(linkRate, 0)} motion packets/s · forwarded ${m.motion_forwarded ?? 0} · rejected ${m.motion_rejected ?? 0}`;
    }
    let state = null, stateAt = 0, online = false, shown = null, shownAt = 0, shownAge = Infinity, followPending = null;
    let frameKey = '', pendingKey = '', imageGeneration = 0, overviewStamp = null, busy = false;
    let lastAck = null, lastEvent = null, actionBusy = false, lastSelection = null;
    const targetButtons = new Map();
    // Decode the next JPEG off-screen, then swap opacity. Replacing the visible
    // <img> caused a compositor flash whenever a physical-camera frame arrived.
    let currentImage = $('camera');
    currentImage.hidden = false;
    currentImage.classList.add('camera-layer', 'active');
    let bufferImage = document.createElement('img');
    bufferImage.className = 'camera-layer';
    bufferImage.alt = '';
    $('camera-view').insertBefore(bufferImage, $('overlay'));
    const ageOfShown = () => shownAge + performance.now() - shownAt;
    const sameProducer = () => shown && state?.output && shown.stream_id === state.output.stream_id && shown.source_id === state.output.source_id;
    const selectable = () => online && performance.now() - stateAt < 750 && state?.vision && sameProducer()
        && ageOfShown() >= 0 && ageOfShown() < selectionWindowMs(state);
    function message(text) { $('message').textContent = text; }
    async function action(name, extra = {}) {
        if (!online || performance.now() - stateAt >= 750) throw Error('Connection is stale. No request sent.');
        // Urgent HOLD/LAND must not wait for an outstanding selection acknowledgement.
        if (actionBusy && !['hold', 'land', 'stop'].includes(name)) return;
        actionBusy = true;
        try {
            const response = await fetch('/api/action', {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: name, ...extra}), signal: AbortSignal.timeout(2500)});
            const data = await response.json();
            if (!response.ok) throw Error(data.error || 'Request rejected');
            message(data.message || 'Request queued — waiting for confirmation.');
            return data;
        } catch (error) { message(error.message); throw error; }
        finally { actionBusy = false; }
    }
    document.querySelectorAll('[data-action]').forEach(button => {
        button.onclick = () => action(button.dataset.action).catch(() => {});
    });
    $('framing-reference').onclick = () => action('framing_reference').catch(() => {});
    $('overlay').onclick = event => {
        if (!selectable()) return message('Wait for a fresh displayed detection before selecting.');
        const rect = event.currentTarget.getBoundingClientRect();
        const point = {x: (event.clientX - rect.left) / rect.width * 1280, y: (event.clientY - rect.top) / rect.height * 720};
        lastSelection = {name: 'select', extra: point, at: performance.now(), retries: 0};
        action('select', {...point, sequence: shown.sequence}).catch(() => {});
    };
    // Double-click = select and follow: the second click has already (re)selected the point; the
    // follow request goes out as soon as the backend reports the identity retained and the
    // aircraft able to follow, or is dropped after the window with a message.
    $('overlay').ondblclick = () => { followPending = performance.now(); message('Follow will start once the target is verified.'); };
    function targets() {
        const tracks = shown?.tracks || [], liveIds = new Set(tracks.map(t => t.id));
        for (const [id, button] of targetButtons) if (!liveIds.has(id)) { button.remove(); targetButtons.delete(id); }
        $('tracks').querySelector('[data-empty]')?.remove();
        for (const t of tracks) {
            let button = targetButtons.get(t.id);
            if (!button) {
                button = document.createElement('button'); targetButtons.set(t.id, button); $('tracks').append(button);
                button.onclick = () => {
                    if (selectable()) {
                        lastSelection = {name: 'select_id', extra: {id: t.id}, at: performance.now(), retries: 0};
                        action('select_id', {id: t.id, sequence: shown.sequence}).catch(() => {});
                    }
                    else message('Displayed frame is too old. Wait for a fresh detection.');
                };
            }
            const selected = t.id === shown.lock?.track_id;
            button.textContent = selected ? 'Selected · ' + t.label + ' · target ' + shown.lock.id : t.label + ' · track ' + t.id;
            button.setAttribute('aria-pressed', String(selected));
            button.disabled = !selectable() || t.coasting || t.ambiguous;
        }
        if (!tracks.length) {
            const empty = document.createElement('span'); empty.dataset.empty = ''; empty.className = 'muted';
            empty.textContent = online ? 'No detections in the displayed frame' : 'Waiting for camera detections';
            $('tracks').replaceChildren(empty);
        }
    }
    function boxes() {
        const ctx = $('overlay').getContext('2d'); ctx.clearRect(0, 0, 1280, 720);
        if (!shown) return;
        const stale = !selectable() || ageOfShown() >= 200;
        if ($('raw-toggle').checked) for (const d of shown.raw_detections || []) {
            ctx.strokeStyle = '#ffaf74'; ctx.lineWidth = 2; ctx.setLineDash([3, 4]);
            ctx.strokeRect(d.x * 1280, d.y * 720, d.w * 1280, d.h * 720);
        }
        for (const t of shown.tracks || []) {
            const selected = t.id === shown.lock?.track_id;
            if ($('filter-toggle').checked && t.filtered_box) {
                const b = t.filtered_box; ctx.strokeStyle = '#c5a4ff'; ctx.setLineDash([5, 5]); ctx.lineWidth = 2;
                ctx.strokeRect(b.x, b.y, b.w, b.h);
            }
            const caution = stale || t.coasting || t.ambiguous;
            ctx.strokeStyle = caution ? '#ffd087' : selected ? '#79e1ba' : '#85b8ff';
            ctx.setLineDash(caution ? [9, 6] : []); ctx.lineWidth = selected ? 4 : 2;
            ctx.strokeRect(t.x, t.y, t.w, t.h);
            const text = selected ? 'TARGET ' + shown.lock.id + ' · ' + t.label : t.label + ' · ' + t.id;
            ctx.font = 'bold 23px system-ui'; const width = Math.min(1280, ctx.measureText(text).width + 18);
            const x = Math.max(0, Math.min(1280 - width, t.x)), y = Math.max(0, Math.min(684, t.y));
            ctx.fillStyle = '#08131eee'; ctx.fillRect(x, y, width, 36); ctx.fillStyle = ctx.strokeStyle;
            ctx.fillText(text, x + 9, y + 26);
        }
        ctx.setLineDash([]);
    }
    $('raw-toggle').onchange = boxes; $('filter-toggle').onchange = boxes;
    function refreshFrame(s) {
        const key = [s.output?.source_id, s.output?.stream_id, s.output?.sequence ?? s.preview_sequence].join(':');
        if (!s.frame_url || key === frameKey || pendingKey) return;
        pendingKey = key; const generation = ++imageGeneration, sampledAt = performance.now();
        const sampleAge = (s.receiver_age_ms ?? Infinity) + Math.max(0, sampledAt - stateAt);
        const image = bufferImage; image.alt = s.pixel_source + ' camera input';
        const timeout = setTimeout(() => { if (generation === imageGeneration) { pendingKey = ''; imageGeneration++; } }, 1000);
        image.onload = () => {
            clearTimeout(timeout);
            if (generation !== imageGeneration) return;
            pendingKey = '';
            if (!online || (s.output && state?.output?.stream_id !== s.output.stream_id)) return;
            currentImage.classList.remove('active');
            image.classList.add('active');
            [currentImage, bufferImage] = [image, currentImage];
            shown = s.output ? {...s.output, raw_detections: s.raw_detections || []} : null;
            shownAt = sampledAt; shownAge = sampleAge; frameKey = key;
            targets(); boxes(); render();
        };
        image.onerror = () => { clearTimeout(timeout); if (generation === imageGeneration) pendingKey = ''; };
        image.src = s.frame_url;
    }
    let zoomOwner = '', zoomFrame = '';
    function inspectTarget() {
        const canvas = $('target-zoom'), ctx = canvas.getContext('2d'), image = currentImage, box = shown?.lock?.box;
        const lock = state?.output?.lock;
        const owner = lock?.id && (lock.identity_retained || lock.identity_locked)
            ? JSON.stringify([state.output.source_id, state.output.stream_id, lock.id]) : '';
        // Keep the last crop through short freshness gaps, but never carry it
        // across target selection, release, identity expiry or producer changes.
        if (owner !== zoomOwner) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            zoomOwner = owner; zoomFrame = '';
        }
        if (!owner || shown?.lock?.id !== lock.id || !shown?.lock?.observation_valid
            || !box || !selectable() || ageOfShown() >= 200 || !image.naturalWidth) {
            $('zoom-note').textContent = zoomFrame
                ? 'Holding last crop · waiting for a fresh target frame.'
                : 'Waiting for a fresh, selected target.';
            return;
        }
        const zoom = Number($('inspect-zoom').value), w = 1280 / zoom, h = 720 / zoom;
        const x = Math.max(0, Math.min(1280 - w, box.x + box.w / 2 - w / 2));
        const y = Math.max(0, Math.min(720 - h, box.y + box.h / 2 - h / 2));
        const cropKey = JSON.stringify([frameKey, zoom, x, y]);
        if (cropKey !== zoomFrame) {
            ctx.drawImage(image, x / 1280 * image.naturalWidth, y / 720 * image.naturalHeight,
                w / 1280 * image.naturalWidth, h / 720 * image.naturalHeight, 0, 0, canvas.width, canvas.height);
            zoomFrame = cropKey;
        }
        $('zoom-note').textContent = zoom + '× display crop. Does not change ISP zoom, inference pixels or control. Physical-camera overlays are approximate.';
    }
    function render() {
        const elapsed = performance.now() - stateAt, view = presentation(state, elapsed, online), s = state || {};
        const lock = s.output?.lock || {}, m = s.mavros, wire = m?.last_wire;
        $('connection').textContent = view.connected ? 'Local demo connected' : 'Disconnected · values may be old';
        $('banner').dataset.tone = view.tone; $('status-title').textContent = view.title; $('next-step').textContent = view.help;
        $('flight').textContent = view.connected ? view.flight : 'Unknown';
        $('altitude').textContent = view.connected ? fmt(s.altitude_m, 1) + ' m altitude' : '—';
        $('takeoff').disabled = !view.canTakeoff; $('follow').disabled = !view.canFollow;
        $('follow').textContent = s.follow_enabled && view.connected ? 'Follow enabled' : 'Enable follow';
        $('hold').disabled = !view.connected; $('land').disabled = !view.canLand; $('stop').disabled = !view.connected;
        $('release').disabled = !view.connected || !lock.id; $('video-stall').disabled = !view.connected || !s.vision;
        $('framing-reference').disabled = !view.connected || !lock.control_valid || view.age >= 200;
        $('selected-target').textContent = view.retained ? 'Target ' + lock.id + ' · ' + (lock.class || 'object') : 'No active target';
        $('selected-detail').textContent = view.retained
            ? (lock.track_id ? 'Detector track ' + lock.track_id + ' can change; ' : '') + 'target ID stays selected.'
            : 'Click a detection in the camera view.';
        $('step-select').dataset.done = view.retained; $('step-takeoff').dataset.done = view.hover;
        $('step-follow').dataset.done = view.connected && !!s.follow_enabled;
        $('identity-state').textContent = view.connected ? view.retained ? 'Retained · ' + (lock.state || 'unknown') : 'Not retained' : 'Unknown';
        $('identity-detail').textContent = view.retained ? 'Target ' + lock.id + ' · not a motion permit' : 'Select a target to begin.';
        $('identity-signal').dataset.tone = view.retained ? 'neutral' : 'warn';
        $('fresh-state').textContent = !view.connected ? 'Unknown' : view.fresh ? 'Fresh request' : s.follow_enabled ? 'HOLD' : 'Follow off';
        $('fresh-detail').textContent = view.connected ? fmt(view.age) + ' ms source age · 200 ms limit' : 'No fresh status received.';
        $('fresh-signal').dataset.tone = view.fresh ? 'good' : 'warn';
        $('wire-state').textContent = !view.connected ? 'Unknown' : !wire ? 'None yet' : wire.allowed ? wire.moving ? 'Motion sent' : 'Zero-motion sent' : 'Rejected';
        $('wire-detail').textContent = !view.connected ? 'Historical values are not live commands.' : wire
            ? (wire.reason || 'no reason reported') + ' · last forwarded ' + fmt((m.forwarded_age_ms ?? Infinity) + elapsed) + ' ms ago'
            : 'A selected target does not imply a sent command.';
        $('wire-signal').dataset.tone = !view.connected || !wire?.allowed ? 'warn' : 'neutral';
        const physical = s.pixel_source?.startsWith('Physical'), recorded = s.pixel_source?.startsWith('Recorded');
        $('camera-title').textContent = physical ? 'Live camera · IMX678' : recorded ? 'Recorded aerial footage' + (s.replay_loops ? ' · loop ' + (s.replay_loops + 1) : '') + (s.replay_paused ? ' · paused' : '') : 'Simulated drone camera';
        const pause = pauseButton(s, view.connected), pauseEl = $('pause-clip');
        pauseEl.hidden = pause.hidden; pauseEl.disabled = pause.disabled; pauseEl.dataset.action = pause.action; pauseEl.textContent = pause.label;
        const due = followDue(view, followPending, performance.now());
        if (due === 'send') { followPending = null; action('follow').catch(() => {}); }
        else if (due === 'expired') { followPending = null; message('Follow not started: the target was not verified within 6 s.'); }
        $('profile-note').textContent = profileText(s, view.connected);
        $('preview-note').textContent = physical
            ? 'Click a detection or choose an ID below. Camera JPEG and overlay timing are approximate.'
            : 'Boxes are paired to the inference image. Choose a target to begin.';
        $('mode-note').textContent = physical || recorded
            ? 'Heading-response demo only. The simulated drone cannot change this fixed input. Forward movement is disabled; distance is not measured.'
            : 'Closed-loop simulation: drone movement changes its camera view. Simulated depth is not physical-camera ranging.';
        const stale = !view.connected || ageOfShown() >= 200;
        $('camera-view').dataset.stale = stale;
        $('frame-notice').hidden = !stale;
        $('frame-notice').textContent = !view.connected ? 'Connection lost · image frozen' : !shown ? 'Waiting for inference'
            : recorded && !s.armed && s.flight !== 'Hover / offboard' ? 'Recorded footage starts at take-off · press Take off, then select'
            : 'Older than control budget · display only';
        $('frame').textContent = shown ? 'Frame ' + shown.sequence + (physical ? ' · approximate overlay' : ' · paired') : 'Preview · no inference';
        $('heading').textContent = view.connected ? fmt(s.heading_deg, 1) + '°' : '—';
        $('requested-heading').textContent = view.connected && s.requested_heading_deg != null ? fmt(s.requested_heading_deg, 1) + '°' : '—';
        const dial = headingDial(s.heading_deg, s.requested_heading_deg, view.connected);
        $('dial-actual').style.transform = dial.actualTransform; $('dial-actual').style.opacity = dial.actualHidden ? '0.25' : '1';
        $('dial-requested').style.transform = dial.requestedTransform; $('dial-requested').style.visibility = dial.requestedHidden ? 'hidden' : 'visible';
        $('dial').setAttribute('aria-label', dial.label);
        appendLinkLog(s.mavros, view.connected);
        $('gazebo-state').textContent = s.gazebo_gui_running && view.connected ? 'Desktop running' : 'No current desktop status';
        $('age').textContent = fmt(view.age) + ' ms'; $('infer').textContent = fmt(s.inference_ms) + ' ms';
        $('passes').textContent = s.detector_passes ?? s.output?.diag?.detector_passes ?? '—';
        $('rtf').textContent = fmt(s.rtf, 2) + '×'; $('range').textContent = s.range_m == null ? 'Unavailable' : fmt(s.range_m, 1) + ' m · simulated';
        $('depth').textContent = s.depth_paired ? 'Exact timestamp · simulated' : 'Unavailable';
        const selected = s.output?.tracks?.find(t => t.id === lock.track_id);
        $('box-source').textContent = selected?.box_source || '—';
        $('identity-candidates').textContent = lock.identity_candidates == null ? '—' : lock.identity_candidates + ' · distances ' + fmt(lock.identity_best_distance, 3) + ' / ' + fmt(lock.identity_runner_up_distance, 3);
        const p = m?.board_publication, n = m?.native_camera;
        $('command-trace').textContent = !view.connected ? 'Disconnected. No previous command values should be treated as live.'
            : 'Control path: ' + (s.transport === 'mavros-15l' ? 'Hailo-15L ROS 2 → MAVROS → local PX4' : 'PC MAVLink → local PX4')
            + '\nROS input: ' + (n ? n.topic + ' · ' + n.ros_received + ' messages · frame ' + n.sequence : 'Rendered/replay observations via ROS bench request')
            + '\nPC request: ' + commandText(s.requested_setpoint)
            + '\nBoard publication: ' + commandText(p?.sp) + ' · ' + fmt((m?.publication_report_age_ms ?? Infinity) + elapsed) + ' ms old'
            + '\nROS ENU: E ' + fmt(p?.ros_enu?.x, 2) + ' · N ' + fmt(p?.ros_enu?.y, 2) + ' m/s · up ' + fmt(p?.ros_enu?.z, 1) + ' m'
            + '\nLast forwarded: ' + commandText(m?.forwarded)
            + '\nMotion packets: ' + (m?.motion_forwarded ?? 0) + ' forwarded / ' + (m?.motion_rejected ?? 0) + ' rejected'
            + '\nBoard reason: ' + (p?.reason || 'Waiting') + '\nPC reason: ' + (s.reason || 'Waiting')
            + '\nRequest → board evaluation: ' + fmt(p?.request_to_publish_ms, 1) + ' ms. Excludes subsequent ROS/wire delivery.'
            + '\nForwarded packets prove sending, not correct target following or actuator response.';
        const framing = s.relative_framing;
        $('framing-readout').textContent = framing?.valid && view.connected
            ? fmt(framing.relative_distance, 2) + '× reference-distance cue. Same pose and focal length assumed; not metres.'
            : framing?.reason || 'Set a reference on a fresh, fully visible target. No safe-distance guarantee.';
        targets(); boxes();
        if ($('inspection-panel').open) inspectTarget();
    }
    async function update() {
        if (busy) return; busy = true;
        const requestStarted = performance.now();
        try {
            const response = await fetch('/api/state', {cache: 'no-store', signal: AbortSignal.timeout(1500)});
            if (!response.ok) throw Error('Console unavailable');
            state = await response.json(); stateAt = requestStarted; online = true;
            refreshFrame(state);
            if (state.overview_ns && state.overview_ns !== overviewStamp) {
                $('overview').src = '/overview.jpg?t=' + state.overview_ns; $('overview').hidden = false; overviewStamp = state.overview_ns;
            }
            const events = state.events || [], ack = events.findLast(e => e.kind === 'selection');
            if (ack && ack.monotonic_ns !== lastAck) {
                if (lastAck !== null) message(ack.detail.ok ? 'Target selection confirmed. Take off or enable follow when ready.' : 'Selection rejected: ' + (ack.detail.error || ack.detail.reason || 'try a fresh detection'));
                if (lastAck !== null && !ack.detail.ok && shouldRetrySelection(ack.detail.error, lastSelection, performance.now())) {
                    // The board refused the click for evidence it is now gathering for that very person
                    // (descriptor budget, or a track observed a moment ago); repeat the same request on a
                    // newer frame, as an operator would, bounded in time and count.
                    const pending = lastSelection; pending.retries += 1;
                    message('Selection retried (' + pending.retries + '): ' + (ack.detail.error || ''));
                    setTimeout(() => { if (lastSelection === pending && selectable()) action(pending.name, {...pending.extra, sequence: shown.sequence}).catch(() => {}); }, 300);
                }
                lastAck = ack.monotonic_ns;
            } else if (lastAck === null) lastAck = 0;
            if (events.at(-1)?.monotonic_ns !== lastEvent) {
                lastEvent = events.at(-1)?.monotonic_ns; $('events').replaceChildren();
                for (const e of events.slice(-30).reverse()) {
                    const li = document.createElement('li'), time = document.createElement('time'); time.textContent = e.time;
                    li.append(time, document.createTextNode(e.kind + ' · ' + (typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail))));
                    $('events').append(li);
                }
            }
        } catch (_) { online = false; }
        finally { busy = false; render(); }
    }
    $('inspect-zoom').onchange = inspectTarget; $('inspection-panel').ontoggle = inspectTarget;
    setInterval(update, 150); setInterval(render, 100); update();
    if (document.modelContext?.registerTool) {
        const lifecycle = new AbortController(); addEventListener('pagehide', () => lifecycle.abort(), {once: true});
        for (const tool of [
            {name: 'read_follow_console', description: 'Read current tracking and simulated flight evidence.',
                inputSchema: {type: 'object', properties: {}, additionalProperties: false}, annotations: {readOnlyHint: true},
                execute: async () => { const r = await fetch('/api/state'); if (!r.ok) throw Error('Console unavailable'); return r.json(); }},
            {name: 'request_simulator_hold', description: 'Queue HOLD for the local simulator, not physical hardware. Queued is not completed.',
                inputSchema: {type: 'object', properties: {}, additionalProperties: false}, annotations: {readOnlyHint: false},
                execute: async () => action('hold')}
        ]) try { Promise.resolve(document.modelContext.registerTool(tool, {signal: lifecycle.signal})).catch(() => {}); } catch (_) {}
    }
}
