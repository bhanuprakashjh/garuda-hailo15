"""Fresh observations -> clock/identity validation -> follow authority. No vehicle I/O."""
from follow_authority import FollowAuthority, AuthorityConfig, target_view
from fresh_target_adapter import from_fresh
from fresh_follow import FreshFollow


class PerceptionAuthority:
    def __init__(self, source_id, stream_id, epoch, *, execution="preview", config=None,
                 framing_translation=False):
        self.follow=FreshFollow(source_id,stream_id,epoch,config=config,
                                framing_translation=framing_translation)
        self.authority=FollowAuthority(AuthorityConfig(execution=execution))
        self.view=dict(state="none",reason="waiting_for_observation",lock_id=None,epoch=epoch,
                       control_valid=False,observation_valid=False,source_id=source_id,stream_id=stream_id)

    def ingest(self, snapshot, started_ns, received_ns):
        try:
            observation=from_fresh(snapshot)
            accepted=self.follow.ingest(observation,started_ns,received_ns)
            self.view=target_view(snapshot)
            return accepted
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            return self.reject("invalid_envelope_"+type(error).__name__)

    def reject(self, reason):
        self.follow.reject(reason)
        self.view=dict(self.view,control_valid=False,observation_valid=False,reason=reason)
        return False

    def tick(self, now_ns):
        decision=self.follow.tick(now_ns)
        v=dict(self.view,control_valid=decision.command.valid,
               observation_valid=decision.command.valid,expires_ns=decision.expires_local_ns or now_ns)
        if not decision.command.valid:
            if v.get('state') == 'tracking':
                v['state'] = "occluded" if v['lock_id'] is not None else "none"
            v['reason'] = decision.command.reason
        return self.authority.update(v,decision.command,now_ns)
