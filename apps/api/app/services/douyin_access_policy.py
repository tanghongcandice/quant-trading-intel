"""Explicit user-confirmed exclusions; absent membership labels prove nothing."""
EXCLUDED = {
    ('douyin_jiujiujiucai', '7686153728089015993'): '7686152973647700197',
    ('douyin_jiujiujiucai', '7696159959458023793'): 'user_removed_unavailable_video',
    ('douyin_panyiyoudianshen', '7692838219910468785'): 'user_removed_no_speech_video',
}

def excluded(source_id, external_id):
    return (source_id, str(external_id)) in EXCLUDED

