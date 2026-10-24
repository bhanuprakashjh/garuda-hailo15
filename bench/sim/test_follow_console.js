'use strict';
const assert = require('node:assert/strict');
const {presentation, headingDial, newLinkEntries, pauseButton, followDue} = require('./follow_console.js');
// Double-click follow: waits for a retained, followable target, sends once, gives up after the window.
assert.equal(followDue({connected: true, retained: true, canFollow: true}, 1000, 1500), 'send');
assert.equal(followDue({connected: true, retained: false, canFollow: false}, 1000, 1500), 'wait');
assert.equal(followDue({connected: true, retained: true, canFollow: false}, 1000, 1500), 'wait', 'Retained but not airborne: keep waiting');
assert.equal(followDue({connected: false, retained: true, canFollow: true}, 1000, 1500), 'wait');
assert.equal(followDue({connected: true, retained: true, canFollow: true}, 1000, 7500), 'expired');
assert.equal(followDue({connected: true, retained: true, canFollow: true}, null, 7500), 'idle');
// Pause: only for a recorded clip, and the one button reports the held state as "Resume".
assert.deepEqual(pauseButton({pixel_source: 'Recorded aerial video', replay_paused: false}, true), {hidden: false, disabled: false, action: 'pause', label: 'Pause clip'});
assert.deepEqual(pauseButton({pixel_source: 'Recorded aerial video', replay_paused: true}, true), {hidden: false, disabled: false, action: 'resume', label: 'Resume clip'});
assert.equal(pauseButton({pixel_source: 'Recorded aerial video'}, false).disabled, true, 'No request while disconnected');
assert.equal(pauseButton({pixel_source: 'Physical IMX678'}, true).hidden, true, 'A live camera cannot be paused');
assert.equal(pauseButton({pixel_source: 'Gazebo RGBD'}, true).hidden, true);
assert.equal(pauseButton(undefined, true).hidden, true);
// Link log: only unseen ids are appended, in id order; malformed entries are ignored.
assert.deepEqual(newLinkEntries([{id: 3, text: 'c'}, {id: 1, text: 'a'}, {id: 2, text: 'b'}], 1).map(e => e.id), [2, 3]);
assert.deepEqual(newLinkEntries([{id: 2}, {text: 'no id'}, null], 5), []);
assert.deepEqual(newLinkEntries(undefined, 0), []);
// Heading dial: actual yaw rotates the drone glyph, requested yaw the ghost arrow; nothing rotates when disconnected.
assert.equal(headingDial(97.34, 101.02).actualTransform, 'rotate(97.3deg)');
assert.equal(headingDial(97.34, 101.02).requestedTransform, 'rotate(101.0deg)');
assert.equal(headingDial(97.34, null).requestedHidden, true, 'No requested heading without a fresh request');
assert.equal(headingDial(97.34, 101.02, false).actualHidden, true, 'Disconnected must not show a stale heading as live');
assert.equal(headingDial(null, 101.02).actualHidden, true);
assert.match(headingDial(97.34, 101.02).label, /97\.3°, requested 101\.0°/);
const state = {flight: 'Hover / offboard', follow_enabled: true, control_request_fresh: true,
    control_request_remaining_ms: 40, receiver_age_ms: 140,
    output: {lock: {id: 7, track_id: 21, identity_retained: true, observation_valid: true, control_valid: true, state: 'tracking'}}};
assert.equal(presentation(state, 10).fresh, true);
assert.equal(presentation(state, 40).fresh, false, 'Original request must expire between polls');
assert.equal(presentation(state, 750).connected, false);
assert.equal(presentation(state, 0, false).canFollow, false);
assert.equal(presentation({...state, receiver_age_ms: null}).fresh, false);
assert.equal(presentation({...state, receiver_age_ms: -1}).fresh, false);
assert.equal(presentation({...state, follow_enabled: false}).fresh, false);
assert.equal(presentation({...state, follow_enabled: false}).canFollow, true,
    'Operator may enable follow; backend still gates each motion request');
assert.equal(presentation({...state, flight: 'Disarmed'}).canTakeoff, true);
assert.equal(presentation({...state, flight: 'Taking off'}).canFollow, false);
assert.equal(presentation({...state, flight: 'Landing'}).canFollow, false);
assert.match(presentation({...state, output: {lock: {id: 7, identity_retained: true, state: 'ambiguous'}}}).title, /waiting for the target/);
assert.equal(presentation({...state, output: {lock: {id: 7, identity_retained: false, state: 'lost'}}}).retained, false);
assert.match(presentation({...state, mavros: {last_wire: {allowed: false}}}).title, /rejected/);
assert.match(presentation(state).title, /requested/, 'Fresh request must not claim delivery');
console.log('Follow console state checks passed');

// Board profile readout: names the model and schedule the board runs on these pixels, never guesses.
const {profileText} = require('./follow_console.js');
const aerial = {board_profile: {path: '/opt/garuda-sim/profile-aerial.json', hef_sha256: 'b70e5a11137abdcf', schedule: 'adaptive',
  follow_local_gap_ms: 1500, follow_global_period_ms: 2000, max_detections: 512}, board_schedule: {mode: 'adaptive', global_pass: false, roi: true, roi_reason: 'requested'}};
assert.equal(profileText(aerial), 'Aerial fine-tune b70e5a11 · tiles while searching · handover 1500 / 2000 ms · cap 512 · this frame: single + ROI (requested)');
assert.equal(profileText({board_profile: {path: '/opt/garuda-sim/profile-fullview.json', hef_sha256: 'aec84f00e4797261', schedule: 'fullview', max_detections: 128}}),
  'Controlled COCO aec84f00 · single view · cap 128');
assert.equal(profileText({pixel_source: 'Physical IMX678 · heading response'}), 'Desk node profile · chosen on the board (fresh_tracking_ctl.sh)');
assert.equal(profileText({}), 'Board profile not reported.');
assert.equal(profileText(aerial, false), 'Board profile unknown while disconnected.');
console.log('Board profile readout checks passed');

// Selection window: recorded replay frames are transport-bound at the PC, so the console must not
// refuse every click on them; live and simulated sources keep the 500 ms rule.
const {selectionWindowMs} = require('./follow_console.js');
assert.equal(selectionWindowMs({pixel_source: 'Recorded aerial video · heading response · assumed FOV'}), 2000);
assert.equal(selectionWindowMs({pixel_source: 'Physical IMX678 · heading response · assumed FOV'}), 500);
assert.equal(selectionWindowMs({pixel_source: 'Gazebo RGBD'}), 500);
assert.equal(selectionWindowMs(undefined), 500);
console.log('Selection window checks passed');

// Selection retry: only for refusals the board resolves by itself, bounded in time and count.
const {shouldRetrySelection} = require('./follow_console.js');
const req = {name: 'select', extra: {x: 1, y: 2}, at: 1000, retries: 0};
assert.equal(shouldRetrySelection('A fresh learned person descriptor is required for identity selection.', req, 1400), true);
assert.equal(shouldRetrySelection('The selected track is not freshly observed. Wait for a live box.', req, 1400), true);
assert.equal(shouldRetrySelection('No confirmed live object at that point. Use target: phone for a phone.', req, 1400), false, 'operator must choose again');
assert.equal(shouldRetrySelection('A fresh learned person descriptor is required', {...req, retries: 5}, 1400), false, 'bounded count');
assert.equal(shouldRetrySelection('A fresh learned person descriptor is required', req, 3100), false, 'bounded time');
assert.equal(shouldRetrySelection('A fresh learned person descriptor is required', null, 1400), false);
console.log('Selection retry checks passed');
