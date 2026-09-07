"""Exclude explicitly identified X/Douyin subscription previews, not truncation alone."""

def enforce_subscription_policy(item):
    if (item.get('source') or {}).get('type') not in {'x', 'douyin'}:
        return
    payload = item.setdefault('raw_payload', {})
    tweet = payload.get('tweet') or {}
    evidence = payload.get('subscription_preview') is True or tweet.get('subscription_preview') is True
    if not evidence:
        return
    payload['analysis_policy'] = {
        'include': False, 'mode': 'review_only', 'reason': 'subscription_preview'
    }
    item['entities'] = []
    item['analysis'] = None
