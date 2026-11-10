# Combined dl6 copy: 045's scheduler adds Policy to the Jobs constructor, so the extracted-class env provides it.
import ast,sys,unittest
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parent.parent.parent/'worker')))
from presets import preset_options,PRESETS
from probe import quality_format
class PresetTests(unittest.TestCase):
 def test_closed_options(self):
  for key in PRESETS:self.assertIn('format',preset_options(key))
  for key in ['raw',{},True,'__proto__']:
   with self.assertRaises(ValueError):preset_options(key)
 def test_strict_height(self):
  self.assertEqual(preset_options('1080p')['format'],'bestvideo[height<=1080]+bestaudio/best[height<=1080]')
  self.assertFalse(quality_format({'height':1080}).endswith('/best'))
 def test_audio(self):
  self.assertEqual(preset_options('audio-m4a')['format'],'bestaudio[ext=m4a]');self.assertEqual(preset_options('audio-opus')['format'],'bestaudio[acodec^=opus]')
 def test_captions(self):
  options=preset_options('subtitles','pt-BR');self.assertTrue(options['writesubtitles']);self.assertFalse(options['writeautomaticsub']);self.assertEqual(options['subtitleslangs'],['pt-BR'])
  for lang in ['all,en','../en','en.*',{},'en;exec']:
   with self.assertRaises(ValueError):preset_options('subtitles',lang)
  with self.assertRaises(ValueError):preset_options('best','en')
 def test_syntax(self):
  for path in ((Path(__file__).resolve().parent.parent.parent/'worker')).glob('*.py'):ast.parse(path.read_text(encoding='utf8'))
 def test_actual_adapter_options(self):
  import types
  from unittest.mock import patch
  module=ast.parse(((Path(__file__).resolve().parent.parent.parent/'worker')/'adapters.py').read_text(encoding='utf8'))
  node=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='PythonYtdlpAdapter')
  env={'Path':Path,'preset_options':preset_options,'install_challenge_provider':lambda:None,'FFmpegAdapter':lambda:types.SimpleNamespace(executable=None)}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-adapter','exec'),env)
  with patch.dict(sys.modules,{'yt_dlp':types.ModuleType('yt_dlp')}):
   options=env['PythonYtdlpAdapter']().options(Path('.'),False,lambda _:None,preset='subtitles',subtitle_lang='de')
  self.assertTrue(options['writesubtitles']);self.assertEqual(options['subtitleslangs'],['de']);self.assertTrue(options['noplaylist'])
 def test_actual_worker_preset_handoff(self):
  import collections,importlib,json,secrets,threading,types
  class History:
   def __init__(self,*args):pass
   def load(self):return {}
   def save(self,*args):pass
  class Thread:
   def __init__(self,*args,**kwargs):pass
   def start(self):pass
  module=ast.parse(((Path(__file__).resolve().parent.parent.parent/'worker')/'worker.py').read_text(encoding='utf8'))
  node=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='Jobs')
  env={'Path':Path,'History':History,'threading':types.SimpleNamespace(Lock=threading.Lock,Condition=threading.Condition,Thread=Thread),'deque':collections.deque,'JDownloaderAdapter':types.SimpleNamespace(from_environment=lambda:types.SimpleNamespace(poisoned=False)),'validate_http_url':lambda u:None,'preset_options':preset_options,'quality_format':quality_format,'json':json,'secrets':secrets,'importlib':importlib,'TERMINAL':{'completed','failed'},'MAX_PENDING':8,'MAX_JOBS':100,'Policy':__import__('schedule_policy').Policy,'_console_offset':lambda path:(lambda now:0),'RateLimiter':__import__('schedule_policy').RateLimiter}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-worker','exec'),env)
  jobs=env['Jobs']('.')
  identity='a'*32
  key=jobs.create('https://example.org/video',True,request_id=identity,preset='audio-opus')
  self.assertTrue(jobs.jobs[key]['audio']);self.assertFalse(jobs.jobs[key]['auto_fallback']);self.assertEqual(jobs.jobs[key]['format'],'bestaudio[acodec^=opus]')
  self.assertEqual(jobs.create('https://example.org/video',True,request_id=identity,preset='audio-opus'),key)
  with self.assertRaises(ValueError):jobs.create('https://example.org/video',True,request_id=identity,preset='best')
  with self.assertRaises(ValueError):jobs.create('https://example.org/video',True,engine='jdownloader',preset='best')
  with self.assertRaises(ValueError):jobs.create('https://example.org/video',True,quality={'height':720},preset='best')
if __name__=='__main__':unittest.main()
