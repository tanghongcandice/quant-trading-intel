#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data/browser_sessions/discord_haochi_daqu.json'
AUTHOR = '好吃好吃啊～～～～～～～～～～～～～'
CHANNEL = '1461938466840379463'
rows = [
 ('1545149797437018252','如果长期的话可以出来先去mu之后回调前再入就行',None),
 ('1545148505922736288',None,'1545148196878032970'),
 ('1545143854322155561','不要羡慕，他们是这种',None),
 ('1545143849100378122',None,'1545143463635456011'),
 ('1545143649778798613','这周看218-220，下周230+ ，高看235-250，低看220',None),
 ('1545143283221794896','又是两倍',None),
 ('1545143276250595411',None,'1545140754685501581'),
 ('1545143174115106817','拿着啦','1545141620658147429'),
 ('1545143096394780734','终于突破210，nbis',None),
 ('1545141049268113418','有位群友在570问我Meta到哪，我说了官司没事看涨615，今天到啦，恭喜你们',None),
 ('1545140477630615652','not much in november, not a big fan of Lisa','1545140398714921162'),
 ('1545140408030330920','how about 8000?','1545139859071565866'),
 ('1545140257077338263','be safe!',None),
 ('1545139902276960286',None,None),
 ('1545139859071565866','okay thanks !',None),
 ('1545124513660936252','你是要怕问我什么时候出现在哪， 提前买了个100倍望远镜， 订了一家5星级酒店顶层盯着我吧，然后暗号是狗狗出现','1545093610821914695'),
 ('1545124289374855229','那个 start hotel tower ride 好玩吗','1545123837874544682'),
 ('1545124065793282150','你真的是。。。。 低俗。。。。',None),
 ('1545123837874544682','这个想法很好啊， grand canyon ！',None),
 ('1545123663768985660','是这一家吗？',None),
 ('1545122381180182648','不用跑',None),
 ('1545122336573751337','昨天说过， 你看看， 还担心的话艾特我，我再回你',None),
 ('1545093357746004088','vegas有什么好玩的？',None),
 ('1545093322056540181','大家想好了吗？',None),
 ('1545088131760525433',None,None),
]
reply_text = {
    '1545143849100378122': '羡慕欧洲的大家能买5倍',
    '1545143276250595411': '我已经全仓nbil 好吃 这次我来冲锋',
    '1545143174115106817': '谢谢好吃，我的本在630,是现在跑还是再等等？',
    '1545140477630615652': '好吃要是去Vegas 查查最近有没有啥演唱会可以看。 我的同事们会专门飞过去看演唱会',
    '1545140408030330920': '我也担心大盘明天拉高 周一周二回踩 毕竟spx都快7800了 难道直接去7900吗 所以才想请问好吃给一些建议',
    '1545124513660936252': '我写给你了，没看到吗？ 🤣 🤣 🤣 🤣 诶，好吃，你多久去LV？我想见你，哪怕远远看看你也行 🫣',
    '1545124289374855229': '打枪跳伞猛男秀',
}
def ts(mid):
    ms = (int(mid) >> 22) + 1420070400000
    return datetime.fromtimestamp(ms/1000, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')

old = json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {'messages': []}
byid = {str(m.get('id')): m for m in old.get('messages', [])}
for mid, content, refid in rows:
    m = {'id': mid, 'timestamp': ts(mid), 'content': content,
         'author': {'name': AUTHOR, 'displayName': AUTHOR}, '_browser_session': True}
    if refid:
        m['reference'] = {'messageId': refid, 'channelId': CHANNEL, 'unavailable': False}
        m['referencedMessage'] = {'id': refid, 'content': reply_text.get(mid), 'author': {'name': None, 'displayName': None}}
    byid[mid] = m
PATH.write_text(json.dumps({'messages': list(byid.values())}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'before': len(old.get('messages', [])), 'after': len(byid), 'added': len(byid)-len(old.get('messages', []))}, ensure_ascii=False))
