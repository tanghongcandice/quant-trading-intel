"""Pure scheduling policy; checks never grant permission before a deadline."""
def gate(state, now):
    if state.get('blocked_reason'):
        return {'status': 'needs_attention', 'reason': state['blocked_reason']}
    deadline = state.get('platform_wait_until', 0) if state.get('local_interval_disabled') else state.get('next_allowed_at', 0)
    delay=max(0, deadline-now)
    if delay:
        return {'status': 'wait_until_due' if delay <= 60 else 'cooldown',
                'wait_seconds': delay, 'next_allowed_at': deadline}
    return None

def success(state):
    state['success_streak']=state.get('success_streak', 0)+1
    state['failure_streak']=0
    if not state.get('local_interval_disabled') and state['success_streak'] >= 4:
        state['interval_seconds']=max(1200, state.get('interval_seconds',2400)-600)
        state['success_streak']=0
    # Existing deadlines are never shortened, including Retry-After.

def failure(state, reason, now, retry_after=0):
    state['success_streak']=0
    state['failure_streak']=state.get('failure_streak',0)+1
    if reason in ('login_required','captcha','ownership_mismatch'):
        state['blocked_reason']=reason
    if retry_after > 0:
        state['platform_wait_until']=max(state.get('platform_wait_until',0),now+retry_after)
    if state.get('local_interval_disabled'):
        state['next_allowed_at']=state.get('platform_wait_until',0)
        state['last_failure']={'reason':reason,'at':now,'retry_after_seconds':retry_after}
        return
    if reason in ('http_403','http_429'):
        base=3600 if reason=='http_403' else 7200
        state['interval_seconds']=min(21600,base*2**min(state['failure_streak']-1,3))
    state['next_allowed_at']=max(state.get('next_allowed_at',0),now+state.get('interval_seconds',2400),now+max(0,retry_after))
    state['last_failure']={'reason':reason,'at':now,'retry_after_seconds':retry_after}
