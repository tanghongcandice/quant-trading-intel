"""Explicit user-confirmed exclusions; absent membership labels prove nothing."""
EXCLUDED = {
    ('douyin_jiujiujiucai', '7686153728089015993'): '7686152973647700197',
}

def excluded(source_id, external_id):
    return (source_id, str(external_id)) in EXCLUDED

