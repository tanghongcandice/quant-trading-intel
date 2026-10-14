import unittest
from capture_douyin_playback import select_media, missing_playback_reason, safe_diagnostics


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.player = {'video_count': 1, 'current_src': 'blob:https://www.douyin.com/player',
                       'title': '公开作品', 'duration': 120, 'sources': []}

    def media(self, path, hint='video_mp4'):
        return {'src': 'https://v11-weba.douyinvod.com/' + path + '?mime_type=' + hint,
                'content_type': 'video/mp4', 'resource_type': 'fetch'}

    def test_mse_fetch_single_video(self):
        media = self.media('video')
        self.assertIsNone(select_media(self.player, [media]))
        player=dict(self.player,appended_sources=[{'src':media['src'],'type':'video/mp4'}])
        self.assertEqual(select_media(player,[media])['src'],media['src'])

    def test_split_mse_audio_not_background_music(self):
        audio = self.media('audio', 'audio_mp4')
        player=dict(self.player,appended_sources=[{'src':audio['src'],'type':'audio/mp4'}])
        selected = select_media(player, [self.media('video'), audio])
        self.assertEqual(selected['src'], audio['src'])
        self.assertEqual(selected['content_type'], 'audio/mp4')
        background = dict(audio, src='https://v11-weba.douyinvod.com/music', content_type='audio/mpeg')
        self.assertIsNone(select_media(self.player, [background]))

    def test_multiple_players_and_ambiguous_streams_rejected(self):
        self.assertIsNone(select_media(dict(self.player, video_count=2), [self.media('video')]))
        self.assertIsNone(select_media(self.player, [self.media('one'), self.media('two')]))

    def test_precise_failure_stages(self):
        self.assertEqual(missing_playback_reason(self.player, []), 'media_response_missing')
        self.assertEqual(missing_playback_reason(dict(self.player, title=''), [1]), 'rendered_title_missing')
        self.assertEqual(missing_playback_reason(dict(self.player, duration=0), [1]), 'duration_missing')
        self.assertEqual(missing_playback_reason({'body': '安全验证'}, []), 'verification_required')
        self.assertEqual(missing_playback_reason({'body': '会员专属'}, []), 'restricted_playback')

    def test_diagnostics_do_not_expose_signed_urls(self):
        diagnostic = safe_diagnostics(dict(self.player, current_src='https://example.com/?token=secret', authors=[]), [], {'profile_url': 'p', 'author_name': 'a'})
        self.assertNotIn('secret', str(diagnostic))


class ActivePlayerTests(unittest.TestCase):
    def test_appended_audio_wins_over_preloaded_video_and_renditions(self):
        active = 'https://v1.douyinvod.com/audio?token=one'
        player = {'video_count':1,'current_src':'blob:player','appended_sources':[
            {'src':active,'type':'audio/mp4; codecs="mp4a.40.2"'}]}
        media = [{'src':url,'content_type':'video/mp4','resource_type':'fetch'} for url in
                 ['https://v1.douyinvod.com/preload',active,'https://v2.douyinvod.com/quality']]
        result=select_media(player,media)
        self.assertEqual(result['src'],active)
        self.assertEqual(result['content_type'],'audio/mp4')

    def test_unattributed_variants_still_fail(self):
        player={'video_count':1,'current_src':'blob:player','appended_sources':[]}
        media=[{'src':'https://v1.douyinvod.com/'+x,'content_type':'video/mp4','resource_type':'fetch'} for x in ['one','two']]
        self.assertIsNone(select_media(player,media))

    def test_login_is_reported_separately(self):
        self.assertEqual(missing_playback_reason({'body':'请登录后观看'},[]),'login_required')

if __name__ == '__main__':
    unittest.main()
