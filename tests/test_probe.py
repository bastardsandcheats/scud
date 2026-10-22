import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from scud.probe import ffprobe, media_tools, test_media_tools as check_tools


class MediaToolTests(unittest.TestCase):
    def test_default_and_custom_paths(self):
        self.assertEqual(media_tools(''), ('ffmpeg', 'ffprobe'))
        self.assertEqual(media_tools('/custom tools/ffmpeg'),
                         ('/custom tools/ffmpeg', '/custom tools/ffprobe'))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(media_tools(directory),
                             (directory+'/ffmpeg', directory+'/ffprobe'))

    @patch('scud.probe.subprocess.run')
    def test_checks_both_versions_without_a_shell(self, run):
        run.side_effect = [Mock(returncode=0, stdout='ffmpeg version test\n'),
                           Mock(returncode=0, stdout='ffprobe version test\n')]
        self.assertTrue(check_tools('/custom tools/ffmpeg')['ok'])
        self.assertEqual(run.call_args_list[0].args[0], ['/custom tools/ffmpeg', '-version'])
        self.assertEqual(run.call_args_list[1].args[0], ['/custom tools/ffprobe', '-version'])
        self.assertNotIn('shell', run.call_args.kwargs)

    @patch('scud.probe.subprocess.run')
    def test_failure_missing_companion_wrong_executable_and_timeout(self, run):
        for error in (FileNotFoundError('missing'), PermissionError('denied'),
                      subprocess.TimeoutExpired('ffmpeg', 8)):
            run.side_effect = error
            self.assertFalse(check_tools('/custom/ffmpeg')['ok'])
        run.side_effect = [Mock(returncode=0, stdout='ffmpeg version test\n'),
                           FileNotFoundError('missing companion')]
        self.assertIn('ffprobe', check_tools('/custom/ffmpeg')['error'])
        run.side_effect = None
        run.return_value = Mock(returncode=0, stdout='unrelated program', stderr='')
        self.assertFalse(check_tools('/bin/true')['ok'])

    @patch('scud.probe.subprocess.run')
    def test_media_probe_uses_selected_installation(self, run):
        run.return_value = Mock(returncode=0, stdout='{"streams":[{"codec_type":"video"}]}')
        data, error = ffprobe('/media/a movie.mkv', '/custom tools/ffmpeg')
        self.assertIsNone(error)
        self.assertTrue(data['streams'])
        self.assertEqual(run.call_args.args[0][0], '/custom tools/ffprobe')
        self.assertEqual(run.call_args.args[0][-1], '/media/a movie.mkv')

    def test_real_tools_and_media_probe(self):
        self.assertTrue(check_tools('/usr/bin/ffmpeg')['ok'])
        with tempfile.TemporaryDirectory() as directory:
            media = str(Path(directory)/'sample.wav')
            with wave.open(media, 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(8000)
                output.writeframes(b'\0\0'*800)
            data, error = ffprobe(media, '/usr/bin/ffmpeg')
            self.assertIsNone(error)
            self.assertEqual(data['streams'][0]['codec_type'], 'audio')


if __name__ == '__main__':
    unittest.main()
