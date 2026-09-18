import copy
import unittest

from group_capture_checkpoint import merge_windows


def capture(rows):
    return {'captured_at': '2026-09-17T03:00:00+00:00', 'messages': rows}


class AlignmentTests(unittest.TestCase):
    def rows(self):
        return [
            {'index': 0, 'duration': '8"', 'voice': '已观察的原生文字'},
            {'index': 1, 'text': '独立边界甲'},
            {'index': 2, 'duration': '3"'},
            {'index': 3, 'text': '独立边界乙'},
        ]

    def test_new_messages_rebase_and_preserve_transcript(self):
        old = self.rows()
        shifted = [dict(r, index=r['index'] + 2, voice='') for r in old]
        result = merge_windows([capture(old), capture(shifted)])
        self.assertEqual([r['index'] for r in result], [2, 3, 4, 5])
        self.assertEqual(result[0]['voice'], old[0]['voice'])
        # A later latest-end observation fills the newly arrived head.
        latest = [{'index': 0, 'text': '新消息一'}, {'index': 1, 'text': '新消息二'}] + shifted
        result = merge_windows([capture(old), capture(shifted), capture(latest)])
        self.assertEqual([r['index'] for r in result], list(range(6)))
        self.assertEqual(result[2]['voice'], old[0]['voice'])

    def test_repeated_duration_only_cannot_rebase(self):
        old = [{'index': i, 'duration': '3"'} for i in range(4)]
        shifted = [dict(r, index=r['index'] + 8) for r in old]
        with self.assertRaises(ValueError):
            merge_windows([capture(old), capture(shifted)])

    def test_changed_message_is_not_hidden_by_rebase(self):
        old = self.rows()
        shifted = [dict(r, index=r['index'] + 2) for r in old]
        shifted[2]['duration'] = '9"'
        with self.assertRaises(ValueError):
            merge_windows([capture(old), capture(shifted)])

    def test_disconnected_windows_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no overlap'):
            merge_windows([capture(self.rows()), capture([{'index': 90, 'text': '另一个窗口'}])])

    def test_repeated_text_sequences_are_ambiguous(self):
        old = [{'index': i, 'text': str(i % 3)} for i in range(9)]
        incoming = [{'index': i + 30, 'text': str(i % 3)} for i in range(3)]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            merge_windows([capture(old), capture(incoming)])


if __name__ == '__main__':
    unittest.main()
