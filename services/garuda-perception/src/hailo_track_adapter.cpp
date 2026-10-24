#include "garuda/hailo_track_adapter.hpp"
#include <algorithm>

namespace garuda {
namespace track {

HailoTrackAdapter::HailoTrackAdapter(int keep_lost_frames, int min_hits,
                                      double dedupe_containment, double dedupe_iou,
                                      double birth_conf,
                                      std::vector<std::string> classes,
                                      int dedupe_protect_age)
    : m_keep_lost(keep_lost_frames), m_min_hits(min_hits),
      m_dedupe_containment(dedupe_containment), m_dedupe_iou(dedupe_iou),
      m_birth_conf(birth_conf), m_classes(std::move(classes)),
      m_dedupe_protect_age(dedupe_protect_age) {}

namespace {

// Fraction of `b`'s own area that overlaps `a`, and the IoU of the pair. bbox is {x, y, w, h} (top-left
// + extent, matching IdDet/TrackRecord throughout this file). A zero-area box reports 0 for both rather
// than dividing by zero.
void overlap_metrics(const double a[4], const double b[4], double& containment_of_b, double& iou) {
    const double ax0 = a[0], ay0 = a[1], ax1 = a[0] + a[2], ay1 = a[1] + a[3];
    const double bx0 = b[0], by0 = b[1], bx1 = b[0] + b[2], by1 = b[1] + b[3];
    const double ix0 = std::max(ax0, bx0), iy0 = std::max(ay0, by0);
    const double ix1 = std::min(ax1, bx1), iy1 = std::min(ay1, by1);
    const double iw = std::max(0.0, ix1 - ix0), ih = std::max(0.0, iy1 - iy0);
    const double inter = iw * ih;
    const double area_a = a[2] * a[3], area_b = b[2] * b[3];
    containment_of_b = area_b > 0.0 ? inter / area_b : 0.0;
    const double uni = area_a + area_b - inter;
    iou = uni > 0.0 ? inter / uni : 0.0;
}

} // namespace

std::vector<TrackRecord> HailoTrackAdapter::update(const std::vector<IdDet>& seen, double ts_ms) {
    // Class allow-list (round 8, Ruling 25), applied first: a detection whose label is not in
    // m_classes is dropped here, BEFORE tsu bookkeeping, the birth gate, or dedupe ever see it -- it
    // cannot create or update an Entry, so it can neither be born itself nor pollute an allowed id's
    // label-majority/born state, nor take part in dedupe. An empty list allows every class (no
    // filtering at all, the pre-round-8 behaviour).
    std::vector<IdDet> filtered;
    const std::vector<IdDet>* use = &seen;
    if (!m_classes.empty()) {
        filtered.reserve(seen.size());
        for (auto& d : seen)
            if (std::find(m_classes.begin(), m_classes.end(), d.label) != m_classes.end())
                filtered.push_back(d);
        use = &filtered;
    }

    // Mark every existing entry missing this frame; a match below resets it back to 0.
    for (auto& e : m_entries) ++e.tsu;

    // Birth gate (round 7, Ruling 24): a detection at or above birth_conf births its id. A
    // non-positive threshold disables the gate outright rather than admitting everything by
    // arithmetic, so a config that sets it to 0 reads as "off" and not as "floor of zero".
    const bool birth_gate_off = m_birth_conf <= 0.0;

    for (auto& d : *use) {
        Entry* found = nullptr;
        for (auto& e : m_entries)
            if (e.id == d.id) { found = &e; break; }
        if (found) {
            found->tsu = 0;
            ++found->hits;
            found->conf = d.conf;
            if (d.conf >= m_birth_conf) found->born = true;   // sticky: a later low-conf frame keeps it
            found->bbox[0] = d.x; found->bbox[1] = d.y; found->bbox[2] = d.w; found->bbox[3] = d.h;
            bool counted = false;
            for (auto& lc : found->label_counts)
                if (lc.first == d.label) { ++lc.second; counted = true; break; }
            if (!counted) found->label_counts.push_back({d.label, 1});
        } else {
            Entry e;
            e.id = d.id; e.conf = d.conf;
            e.bbox[0] = d.x; e.bbox[1] = d.y; e.bbox[2] = d.w; e.bbox[3] = d.h;
            e.tsu = 0; e.hits = 1;
            e.born = birth_gate_off || d.conf >= m_birth_conf;
            e.emits = 0;   // round 9: frames since first emission, counted in the emit loop below
            e.first_seen_ms = ts_ms;   // round 10: stamped once, at ANY conf, after the allow-list
            e.label_counts.push_back({d.label, 1});
            m_entries.push_back(e);          // appended at the back -> stays in first-seen order
        }
    }

    // Drop ids missing longer than keep_lost_frames. remove_if/erase is stable, so the surviving
    // entries keep their relative (first-seen) order.
    m_entries.erase(std::remove_if(m_entries.begin(), m_entries.end(),
                                    [this](const Entry& e) { return e.tsu > m_keep_lost; }),
                     m_entries.end());

    // Round 9 (Ruling 26): live_raw() -- this frame's LIVE records after the class allow-list and
    // NOTHING else. Built here, before the birth gate and the dedupe pass below, because those two
    // are display gates: they decide what is drawn and what may become a NEW lock, not what an
    // EXISTING lock may keep tracking. See the class comment for the full argument.
    m_live_raw.clear();
    for (auto& e : m_entries) {
        if (e.tsu != 0) continue;
        m_live_raw.push_back({e.id, e.cls(), e.conf,
                               {e.bbox[0], e.bbox[1], e.bbox[2], e.bbox[3]},
                               0, e.hits >= m_min_hits, e.first_seen_ms});
    }

    // Unborn ids are skipped here, i.e. BEFORE the dedupe pass below ever sees them: a junk detection
    // that never cleared birth_conf can neither be published nor suppress a real track.
    std::vector<TrackRecord> out;
    std::vector<int> age;           // round 9: out[i]'s frames-since-first-emission, parallel to `out`
    out.reserve(m_entries.size());
    age.reserve(m_entries.size());
    for (auto& e : m_entries) {
        if (!birth_gate_off && !e.born) continue;
        out.push_back({e.id, e.cls(), e.conf,
                        {e.bbox[0], e.bbox[1], e.bbox[2], e.bbox[3]},
                        e.tsu, e.hits >= m_min_hits, e.first_seen_ms});
        age.push_back(e.emits);     // read BEFORE the increment -> "frames since first emission"
        ++e.emits;
    }

    // Duplicate same-class LIVE track dedupe (on-board fix round 6, Ruling 23) -- see the class
    // comment above for the mechanism. Coasting records (tsu > 0) are never touched: excluded from
    // `live_idx` below, so they're neither a candidate to be dropped nor a comparator that can drop
    // something else.
    if (m_dedupe_containment > 0.0 || m_dedupe_iou > 0.0) {
        std::vector<size_t> live_idx;
        for (size_t i = 0; i < out.size(); ++i)
            if (out[i].time_since_update == 0) live_idx.push_back(i);

        // Deterministic order: larger box first. Ties (equal area) fall back to std::sort's own
        // ordering -- harmless, since which of two equal-area boxes is nominally "a" vs "b" changes
        // neither overlap_metrics' containment/IoU values (symmetric up to the label) nor which one
        // the rules below choose to drop.
        std::sort(live_idx.begin(), live_idx.end(), [&out](size_t a, size_t b) {
            return out[a].bbox[2] * out[a].bbox[3] > out[b].bbox[2] * out[b].bbox[3];
        });

        // Round 9 (Ruling 27): whether a record is ELIGIBLE to be suppressed at all. The locked
        // identity never is, and neither is a track that has already been published for
        // dedupe_protect_age frames -- by then it is an established identity, not a duplicate birth,
        // and "a smaller box mostly inside a larger one" is at least as likely to be one person
        // standing behind another as one person detected twice. A non-positive dedupe_protect_age
        // disables the age half (pre-round-9 behaviour for everything except the protected id).
        auto may_drop = [&](size_t k) {
            if (m_protected_id >= 0 && out[k].id == m_protected_id) return false;
            if (m_dedupe_protect_age <= 0) return true;
            return age[k] < m_dedupe_protect_age;
        };

        std::vector<bool> dropped(out.size(), false);
        for (size_t ii = 0; ii < live_idx.size(); ++ii) {
            const size_t i = live_idx[ii];
            if (dropped[i]) continue;   // a record dropped once is not considered further
            for (size_t jj = ii + 1; jj < live_idx.size(); ++jj) {
                const size_t j = live_idx[jj];   // area[j] <= area[i] by the sort above
                if (dropped[j] || out[i].cls != out[j].cls) continue;

                double containment_of_j, iou;
                overlap_metrics(out[i].bbox, out[j].bbox, containment_of_j, iou);

                if (m_dedupe_containment > 0.0 && containment_of_j >= m_dedupe_containment) {
                    // (a): the smaller box is mostly inside the larger one -- dropped only if it is
                    // still young and unprotected; otherwise BOTH survive and this pair is settled.
                    if (may_drop(j)) dropped[j] = true;
                    continue;
                }
                if (m_dedupe_iou > 0.0 && iou >= m_dedupe_iou) {
                    // (b): high overlap, neither mostly inside the other -- keep the higher-confidence
                    // record. A tie keeps `i` (already the larger-or-equal-area box, deterministic).
                    // If the record that would lose is protected or established, neither is dropped.
                    if (out[i].conf < out[j].conf) {
                        if (may_drop(i)) { dropped[i] = true; break; }
                    } else if (may_drop(j)) {
                        dropped[j] = true;
                    }
                }
            }
        }

        if (std::any_of(dropped.begin(), dropped.end(), [](bool d) { return d; })) {
            std::vector<TrackRecord> filtered;
            filtered.reserve(out.size());
            for (size_t i = 0; i < out.size(); ++i)
                if (!dropped[i]) filtered.push_back(out[i]);
            out.swap(filtered);
        }
    }

    return out;
}

} // namespace track
} // namespace garuda
