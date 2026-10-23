import unittest
import tempfile
from pathlib import Path
import core


class SubtitleTests(unittest.TestCase):
    def test_learned_breaks_match_recognition_punctuation_and_simplified_text(self):
        profile = core.new_profile('宣传片')
        core.learn(profile, [{'start': 0, 'end': 2, 'text': '我們一起出發'}, {'start': 2, 'end': 4, 'text': '去看看世界'}], '成稿')
        cues = core.resegment([{'start': 10, 'end': 15, 'text': '我们一起出发，去看看世界。'}], profile)
        self.assertEqual([c['text'] for c in cues], ['我们一起出发', '去看看世界'])
        self.assertEqual(cues[0]['start'], 10)
        self.assertEqual(cues[-1]['end'], 15)

    def test_simplify_preserves_timing_linebreaks_and_original_text(self):
        cues = [{'start': 167.0, 'end': 170.5, 'text': '戰略之助動力電池\nAI 技術 2026'}]
        result = core.simplify_cues(cues)
        self.assertEqual(result, [{'start': 167.0, 'end': 170.5, 'text': '战略之助动力电池\nAI 技术 2026'}])
        self.assertEqual(cues[0]['text'], '戰略之助動力電池\nAI 技術 2026')

    def test_simplify_word_alignment_uses_full_phrase_context(self):
        cue = {'start': 0, 'end': 3, 'text': '乾坤和頭髮', 'words': [
            {'start': 0, 'end': .4, 'word': '乾'},
            {'start': .4, 'end': 1, 'word': '坤和'},
            {'start': 1, 'end': 3, 'word': '頭髮'}]}
        result = core.simplify_cues([cue])[0]
        self.assertEqual(result['text'], '乾坤和头发')
        self.assertEqual([w['word'] for w in result['words']], ['乾', '坤和', '头发'])
        self.assertEqual([(w['start'], w['end']) for w in result['words']], [(0, .4), (.4, 1), (1, 3)])

    def test_simplify_is_idempotent_and_leaves_english_unchanged(self):
        cues = [{'start': 0, 'end': 1, 'text': '动力电池 / Hello, AI!'}]
        self.assertEqual(core.simplify_cues(core.simplify_cues(cues)), cues)

    def test_srt_roundtrip_multiline_and_milliseconds(self):
        cues = core.parse_subtitles('\ufeff1\r\n00:00:01,125 --> 00:00:03,250\r\n你好\r\n世界\r\n')
        self.assertEqual(cues, [{'start': 1.125, 'end': 3.25, 'text': '你好\n世界'}])
        self.assertEqual(core.parse_subtitles(core.to_srt(cues)), cues)

    def test_gb18030_subtitle_file_is_decoded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.srt'
            path.write_bytes('1\n00:00:00,000 --> 00:00:01,000\n你好世界\n'.encode('gb18030'))
            self.assertEqual(core.read_subtitles(path)[0]['text'], '你好世界')

    def test_ass_uses_declared_columns_and_strips_override_tags(self):
        cues = core.parse_subtitles('[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,{\\b1}你好\\Nworld, again', '.ass')
        self.assertEqual(cues[0]['text'], '你好\nworld, again')
        self.assertEqual(cues[0]['end'], 2.5)

    def test_invalid_ranges_and_overlap_are_rejected(self):
        for cues in ([{'start': -1, 'end': 2, 'text': 'a'}], [{'start': 2, 'end': 1, 'text': 'a'}], [{'start': 0, 'end': 2, 'text': 'a'}, {'start': 1, 'end': 3, 'text': 'b'}]):
            with self.assertRaises(ValueError):
                core.validate_cues(cues)

    def test_learning_deduplicates_and_separates_lines_from_cues(self):
        profile = core.new_profile('口播')
        cues = [{'start': 0, 'end': 2, 'text': '今天我们\n去看海'}, {'start': 2, 'end': 4, 'text': '然后回家'}]
        core.learn(profile, cues, '作品一')
        core.learn(profile, cues, '作品一')
        self.assertEqual(len(profile['samples']), 1)
        self.assertEqual(profile['stats']['cue_count'], 2)
        self.assertEqual(profile['stats']['multiline_count'], 1)

    def test_exact_learned_break_is_reused_and_timing_is_preserved(self):
        profile = core.new_profile('口播')
        core.learn(profile, [{'start': 0, 'end': 2, 'text': '今天我们去看海'}, {'start': 2, 'end': 4, 'text': '然后回家'}], '作品一')
        result = core.resegment([{'start': 10, 'end': 21, 'text': '今天我们去看海然后回家'}], profile)
        self.assertEqual([c['text'] for c in result], ['今天我们去看海', '然后回家'])
        self.assertEqual(result[0]['start'], 10)
        self.assertEqual(result[-1]['end'], 21)
        self.assertEqual(result[0]['end'], result[1]['start'])

    def test_new_text_preserves_words_protected_terms_and_pauses(self):
        profile = core.new_profile('口播')
        profile['rules'].update(target_chars=6, max_chars=8, protected_terms=['人工智能'])
        source = [{'start': 0, 'end': 5, 'text': '欢迎学习人工智能课程'}, {'start': 9, 'end': 12, 'text': 'hello world again'}]
        result = core.resegment(source, profile)
        self.assertEqual(''.join(c['text'].replace('\n', '') for c in result), '欢迎学习人工智能课程hello world again')
        self.assertTrue(any('人工智能' in c['text'] for c in result))
        self.assertFalse(any(c['start'] < 9 and c['end'] > 5 for c in result))

    def test_word_timestamps_used_for_breaks(self):
        profile = core.new_profile('口播')
        profile['rules'].update(target_chars=2, max_chars=2)
        cues = [{'start': 0, 'end': 8, 'text': '你好世界', 'words': [{'word': '你好', 'start': 0, 'end': 1}, {'word': '世界', 'start': 6, 'end': 8}]}]
        result = core.resegment(cues, profile)
        self.assertEqual([c['text'] for c in result], ['你好', '世界'])
        self.assertEqual(result[0]['end'], 1)
        self.assertEqual(result[1]['start'], 6)

    def test_ass_export_escapes_injection_and_preserves_resolution(self):
        result = core.to_ass([{'start': 0, 'end': 1, 'text': '{\\pos(0,0)}你好\n世界'}], {}, 1080, 1920)
        self.assertIn('PlayResY: 1920', result)
        self.assertNotIn('{\\pos(0,0)}', result)
        self.assertIn('你好\\N世界', result)

    def test_store_roundtrip_and_invalid_project_does_not_replace_autosave(self):
        with tempfile.TemporaryDirectory() as folder:
            store = core.Store(Path(folder))
            project = core.new_project()
            project['cues'] = [{'start': 0, 'end': 1, 'text': '测试'}]
            store.save_project(project)
            self.assertEqual(store.load_project()['cues'][0]['text'], '测试')
            project['cues'][0]['end'] = -1
            with self.assertRaises(ValueError):
                store.save_project(project)
            self.assertEqual(store.load_project()['cues'][0]['end'], 1)


if __name__ == '__main__':
    unittest.main()
