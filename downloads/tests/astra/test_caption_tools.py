import unittest,sys
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parent.parent.parent/'worker')))
import caption_tools as c
class Captions(unittest.TestCase):
 def test_selection(self):
  tracks=c.tracks({'subtitles':{'en':[{'url':'https://media.example/c.vtt','ext':'vtt'},{'url':'file:///private','ext':'srt'},{'url':'https://media.example/c.ttml','ext':'ttml'}]},'automatic_captions':{'de':[{'url':'https://media.example/auto.vtt','ext':'vtt'}]}})
  self.assertEqual(len(tracks),1);self.assertNotIn('url',c.public_rows(tracks)[0]);key=next(iter(tracks));calls=[]
  def fetch(url,**kwargs):calls.append(kwargs);return b'WEBVTT\n\n00:01.000 --> 00:02.000\nHello\n'
  self.assertIn('Hello',c.download(key,tracks,fetch)['text']);self.assertEqual(calls[0],{'max_bytes':1048576,'timeout_seconds':15})
  with self.assertRaises(ValueError):c.download('unknown',tracks,fetch)
  with self.assertRaises(ValueError):c.download(key,tracks,lambda *a,**k:b'x'*(c.MAX_BYTES+1))
  with self.assertRaises(UnicodeDecodeError):c.download(key,tracks,lambda *a,**k:b'\xff')
 def test_options(self):
  opts=c.extraction_options();self.assertTrue(opts['skip_download']);self.assertFalse(opts['writesubtitles']);self.assertFalse(opts['writeautomaticsub'])
if __name__=='__main__':unittest.main()
