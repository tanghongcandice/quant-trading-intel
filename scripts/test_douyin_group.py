import copy
import json
import unittest
from pathlib import Path
from build_douyin_group import build

class GroupTests(unittest.TestCase):
    def setUp(self):
        self.payload={'group_name':'宇菠萝的认知圈1群','captured_at':'2026-09-07T04:00:00Z','messages':[
            {'index':5,'time':'昨天 21:48','author':'甲','role':'管理员','text':'昨天 21:48\n甲\n周复盘'},
            {'index':4,'duration':'2"','voice':'先说消息。'},
            {'index':3,'duration':'3"','voice':'这是解释。'},
            {'index':2,'author':'乙','role':'群主','duration':'4"','voice':'另一人的观点。'},
            {'index':1,'text':'文字打断'},
            {'index':0,'duration':'2"','voice':'再次补充。'}], 'voice_paragraph_starts':[4]}
    def test_order_speakers_and_text_boundaries(self):
        voices=[i for i in build(self.payload) if i['raw_payload']['transcription']['audio_count']]
        self.assertEqual([i['content']['text'] for i in voices],['先说消息。这是解释。','另一人的观点。','再次补充。'])
        self.assertEqual(voices[1]['author']['display_name'],'乙')
    def test_missing_asr_fails(self):
        del self.payload['messages'][1]['voice']
        with self.assertRaises(ValueError):build(self.payload)
    def test_video_metadata_preserves_identity_and_separates_creator(self):
        self.payload['messages']=[{'index':1,'time':'昨天 18:21','author':'甲','role':'群主','text':'昨天 18:21\n甲\n宇菠萝','images':[{'url':'https://example.com/cover.jpg'}]}]
        original=build(self.payload)[0]
        self.payload['messages'][0].update(message_kind='video_share',shared_video={
            'url':'https://www.douyin.com/video/7682361511919467194','title':'视频标题','author':'宇菠萝'})
        item=build(self.payload)[0]
        self.assertEqual(item['id'],original['id'])
        self.assertEqual(item['author']['display_name'],'甲')
        self.assertEqual(item['external']['url'],'https://www.douyin.com/video/7682361511919467194')
        self.assertEqual(item['content']['text'],'视频标题\n\n视频作者：宇菠萝\n\nhttps://www.douyin.com/video/7682361511919467194')
    def test_video_without_link_fails(self):
        self.payload['messages'][0]['message_kind']='video_share'
        with self.assertRaises(ValueError):build(self.payload)
    def test_automatic_publish_notice_excluded(self):
        self.payload['messages']=[self.payload['messages'][0],{'index':0,'text':'我发布了新作品，快来看看！'}]
        self.assertEqual(len(build(self.payload)),1)
        self.payload['messages'][1].update(message_kind='system_notice',text='群公告已更新')
        self.assertEqual(len(build(self.payload)),1)
    def test_new_message_does_not_change_old_ids(self):
        old=build(self.payload)
        for row in self.payload['messages']:row['index']+=1
        self.payload['voice_paragraph_starts']=[5]
        self.payload['messages'].append({'index':0,'time':'10:00','author':'甲','role':'管理员','text':'新增消息'})
        self.assertEqual([i['id'] for i in old],[i['id'] for i in build(self.payload)[:-1]])
    def test_member_and_system_excluded(self):
        self.payload['messages'][0]['role']='普通成员'
        self.payload['messages'].append({'index':-1,'time':'10:00','text':'新人 加入了群聊，新成员可查看历史消息'})
        rows=build(self.payload)
        self.assertTrue(all(i['author']['display_name']=='乙' for i in rows))
        self.assertTrue(all('加入了群聊' not in i['content']['text'] for i in rows))

    def test_wrong_group_rejected(self):
        self.payload['group_name']='其他群'
        with self.assertRaises(ValueError):build(self.payload)
    def test_missing_indices_not_merged(self):
        self.payload['messages'].pop(2)
        self.payload['messages'][2].pop('author')
        voices=[i for i in build(self.payload) if i['raw_payload']['transcription']['audio_count']]
        self.assertEqual(len(voices),3)

if __name__=='__main__':unittest.main()
