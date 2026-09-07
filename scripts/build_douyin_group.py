#!/usr/bin/env python3
"""Build A-share items from authorized rendered group captures; never invent ASR.

DOM indices are snapshot-local ordering only, never persistent message IDs.
All source fragments remain in raw_payload for auditing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = 'douyin_group_yuboluo_1'
GROUP = '宇菠萝的认知圈1群'
TZ = timezone(timedelta(hours=8))

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def resolve_time(label, captured):
    relative = re.fullmatch(r'(\d+)分钟前', label)
    if relative or label == '刚刚':
        value = captured - timedelta(minutes=int(relative[1]) if relative else 0)
        return value.replace(second=0, microsecond=0).isoformat()
    day = captured.date()
    if '前天' in label: day -= timedelta(days=2)
    elif '昨天' in label: day -= timedelta(days=1)
    elif re.search(r'周[一二三四五六日天]', label):
        weekday = re.search(r'周([一二三四五六日天])', label)[1]
        target = '一二三四五六日'.index(weekday.replace('天', '日'))
        day -= timedelta(days=(day.weekday() - target) % 7)
    elif re.search(r'\d{2}/\d{2}', label):
        m = re.search(r'(\d{2})/(\d{2})', label)
        day = day.replace(month=int(m[1]), day=int(m[2]))
        if day > captured.date(): day = day.replace(year=day.year-1)
    tm = re.search(r'(\d{1,2}):(\d{2})', label)
    hour, minute = (int(tm[1]), int(tm[2])) if tm else (0, 0)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()

def paragraphs(parts, starts):
    result = []
    for part in parts:
        text = part['voice'].strip()
        if not result or part['index'] in starts:
            result.append(text)
        else:
            result[-1] += text
    return '\n\n'.join(result)

def build(payload):
    if payload.get('group_name') != GROUP:
        raise ValueError('Wrong group')
    captured = datetime.fromisoformat(payload['captured_at'].replace('Z', '+00:00')).astimezone(TZ)
    rows = sorted(payload['messages'], key=lambda x: x['index'], reverse=True)
    if len({r['index'] for r in rows}) != len(rows): raise ValueError('Duplicate snapshot indices')
    starts = set(payload.get('voice_paragraph_starts', []))
    items, occurrences = [], {}
    current_time, current_author, current_speaker = None, None, None
    voice_run = []
    current_role, current_topic = None, None

    def emit(parts, voice=False):
        first = parts[0]
        if first.get('sender_role') not in {'群主', '管理员'}:
            return
        if voice:
            text = paragraphs(parts, starts or {p['index'] for p in parts})
            title = f"{first.get('topic') or '群聊语音'} · {len(parts)}段语音合并（抖音转写）"
        else:
            text = first.get('body', '').strip()
            title = '群聊消息'
        system = '加入了群聊' in text
        media = not voice and bool(first.get('media_images'))
        if system: title = '群聊通知'
        if media: title = '群聊分享'
        shared_video = first.get('shared_video')
        if first.get('message_kind') == 'video_share' and not shared_video:
            raise ValueError('Video share needs an observed video URL: '+str(first['index']))
        if shared_video:
            if not re.fullmatch(r'https://www\.douyin\.com/video/\d+', shared_video.get('url', '')):
                raise ValueError('Invalid video URL')
            title = '群聊视频分享'
            text = '\n\n'.join(filter(None, [shared_video.get('title') or '分享视频',
                '视频作者：'+shared_video['author'] if shared_video.get('author') else None,
                shared_video['url']]))
        if not text: text = '[分享内容：网页未提供可提取正文]'
        author = '群系统通知' if system else first.get('sender') or '发送者未显示'
        created = first['created_at']
        # The UI only exposes minute/day separators. Preserve precision explicitly.
        identity = json.dumps([SOURCE, created, first.get('speaker'), [p.get('voice', p.get('body')) for p in parts]], ensure_ascii=False)
        occurrences[identity] = occurrences.get(identity, 0) + 1
        key = digest(identity + ':' + str(occurrences[identity]))[:24]
        review = system or media or not voice
        items.append({
            'schema_version':'information_item.v1', 'id':'itm_'+key,
            'source':{'id':SOURCE,'type':'douyin','name':'抖音群聊 '+GROUP,'collector':'authorized-rendered-group+douyin-native-asr','tags':['market:cn','group_chat']},
            'external':{'id':key,'url':shared_video['url'] if shared_video else 'https://www.douyin.com/chat','thread_id':GROUP},
            'author':{'handle':author,'display_name':author},
            'content':{'title':title,'text':text,'language':'zh','hash':digest(text)},
            'timestamps':{'created_at':created,'collected_at':payload['captured_at']},
            'entities':[], 'relations':{},
            'raw_payload':{'market':'cn','group_name':GROUP,'message_parts':parts,'sender_role':first['sender_role'],
                'group_url':'https://www.douyin.com/chat','shared_video':shared_video,
                'timestamp_precision':'inherited_ui_separator','history_complete':payload.get('history_complete',False),
                'history_boundary':payload.get('history_boundary'),
                'transcription':{'method':'douyin_native_asr','audio_count':len(parts) if voice else 0,'verbatim_preserved':True,'human_audio_verified':False},
                'analysis_policy':{'include':not review,'mode':'review_only' if review else 'analysis','reason':'group_notice_or_unparsed_share' if review else None}},
            'ingestion':{'dedupe_key':SOURCE+':'+key}
        })

    def flush():
        if voice_run:
            emit(voice_run[:], True)
            voice_run.clear()

    for row in rows:
        r = dict(row)
        if r.get('time'):
            next_time = resolve_time(r['time'], captured)
            if next_time != current_time: flush()
            current_time = next_time
        if r.get('message_kind') == 'system_notice' or (not r.get('author') and (
            '加入了群聊' in r.get('text', '') or r.get('text', '').strip() == '我发布了新作品，快来看看！')):
            flush()
            current_author = current_speaker = current_role = current_topic = None
            continue
        if r.get('author'):
            speaker = next((i['url'].split('?')[0] for i in r.get('images',[]) if 'aweme-avatar' in i['url']), r['author'])
            if speaker != current_speaker: flush()
            current_author, current_speaker = r['author'], speaker
            label_text = r.get('text', '')
            if r.get('time'): label_text = label_text.removeprefix(r['time']).lstrip()
            label_text = label_text.removeprefix(r['author']).lstrip()
            role_match = re.match(r'^(群主|管理员)(?:\s|$)', label_text)
            current_role = r.get('role') or (role_match[1] if role_match else None)
            current_topic = None
        r.update(sender=current_author, speaker=current_speaker, created_at=current_time, sender_role=current_role, topic=current_topic)
        if current_role not in {"群主", "管理员"}:
            flush()
            continue
        if not current_time:
            raise ValueError('Oldest row needs an observed date separator')
        if r.get('duration'):
            if not r.get('voice'): raise ValueError('Untranscribed voice: '+str(r['index']))
            if not current_author: raise ValueError('Voice sender is unknown')
            if voice_run and voice_run[-1]['index'] - r['index'] != 1:
                flush()
            voice_run.append(r)
            continue
        flush()
        body = r.get('text','')
        if r.get('time'): body = body.removeprefix(r['time']).lstrip()
        if r.get('author'):
            body = body.removeprefix(r['author']).lstrip()
            body = re.sub(r'^(群主|管理员)\s*', '', body)
        current_topic = body.strip() if body.strip() in {'周复盘', '日复盘', '盘前', '盘后复盘'} else None
        r['body'] = body
        r['media_images'] = [i for i in r.get('images',[]) if 'aweme-avatar' not in i['url']]
        emit([r])
    flush()
    return items

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,default=Path('data/browser_sessions/douyin_group_yuboluo_1.json'))
    p.add_argument('--output',type=Path,default=Path('data/douyin_built/yuboluo_group_1.jsonl'))
    args=p.parse_args()
    payload=json.loads(args.snapshot.read_text())
    items=build(payload)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in items))
    print(json.dumps({'items':len(items),'raw_messages':len(payload['messages']),'history_complete':payload.get('history_complete',False)},ensure_ascii=False))
if __name__=='__main__':main()
