"""Reference for the C++ LockResolver: mono's lock/coast/re-acquire loop and click/target handlers,
lifted verbatim from feat/portal-tracking:hosts/pi5/garuda_mono.py (loop body lines 229-249, POST handlers 487-512).
Constants as mono runs them: MAX_LOST=25, REACQ=5, default class "person"."""
MAX_LOST, REACQ = 25, 5

def step_lock(tracker, lid, want_cls):
    """One frame after tracker.update(): returns (lid, coasting, alive) exactly as mono computes them."""
    alive = [t for t in tracker.tracks if t.confirmed and t.time_since_update <= MAX_LOST]
    locked = next((t for t in alive if t.track_id == lid), None) if lid is not None else None
    if locked is None and want_cls:
        cands = [t for t in alive if t.cls == want_cls]
        if cands:
            locked = max(cands, key=lambda t: (t.time_since_update == 0, t.conf))
    elif locked is not None and locked.time_since_update > REACQ and want_cls:
        live = [t for t in alive if t.cls == want_cls and t.time_since_update == 0]
        if live:
            locked = max(live, key=lambda t: t.conf)
    lid = locked.track_id if locked is not None else None
    coasting = (locked.time_since_update > 0) if locked is not None else False
    return lid, coasting, alive

def click(tracks_full, cx, cy):
    """mono's /api/mono_click: prefer the smallest box under the click, else the nearest centre. Returns (tid, label) or None."""
    picked, best_key = None, None
    for tid, lbl, x, y, w, h, *_ in tracks_full:
        inside = (x <= cx <= x + w) and (y <= cy <= y + h)
        d2 = (x + w / 2 - cx) ** 2 + (y + h / 2 - cy) ** 2
        key = (0, w * h) if inside else (1, d2)
        if best_key is None or key < best_key:
            best_key, picked = key, (tid, lbl)
    return picked

def tracks_full_of(alive):
    return [(t.track_id, t.cls, t.bbox[0], t.bbox[1], t.bbox[2], t.bbox[3], float(t.conf), t.time_since_update > 0) for t in alive]
