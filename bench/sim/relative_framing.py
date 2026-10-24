"""Monocular framing diagnostic, never a metric range or flight clearance."""
import math


class RelativeFraming:
    def __init__(self):
        self.reference = None
        self.identity = None

    def sample(self, out, *, set_reference=False):
        base = dict(valid=False, metric_range=False, translation_authorized=False,
                    reason='fresh, fully visible selected target required')
        if not out:
            return base
        lock = out.get('lock', {})
        identity = (out.get('source_id'), out.get('stream_id'), lock.get('epoch'), lock.get('id'),
                    out.get('frame', {}).get('width'), out.get('frame', {}).get('height'))
        if identity != self.identity:
            self.reference = None
            self.identity = identity
        b = lock.get('box')
        if not lock.get('control_valid') or not lock.get('observation_valid') or not b or lock.get('state') != 'tracking':
            return base
        width, height = identity[-2:]
        if not width or not height:
            return base
        vals = [b.get(k) for k in ('x', 'y', 'w', 'h')]
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in vals):
            return base
        x, y, w, h = vals
        if min(w, h) <= 0 or x < width*.01 or y < height*.01 or x+w > width*.99 or y+h > height*.99:
            return dict(base, reason='box clipped or too close to image edge')
        if set_reference:
            self.reference = (h/height, w/h)
        if self.reference is None:
            return dict(base, reason='set a framing reference; no distance in metres')
        if not .7 <= (w/h)/self.reference[1] <= 1.3:
            return dict(base, reason='pose/aspect changed; relative scale unreliable')
        return dict(base, valid=True, reason='apparent size only; fixed pose and focal length assumed',
                    relative_distance=self.reference[0]/(h/height),
                    height_fraction=h/height, reference_height_fraction=self.reference[0])
