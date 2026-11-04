import ast,contextlib,datetime,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parent.parent.parent/'worker')))
from schedule_policy import Policy,RateLimiter,DEFAULT,validate
class Tests(unittest.TestCase):
 def test_overnight_day_boundary(self):
  p=Policy();p.save(dict(DEFAULT,enabled=True,days=[4]))
  for text,allowed in [('2026-11-06T21:59:00+00:00',False),('2026-11-06T22:00:00+00:00',True),('2026-11-07T05:59:00+00:00',True),('2026-11-07T06:00:00+00:00',False),('2026-11-07T22:00:00+00:00',False)]:self.assertEqual(p.allow_start(datetime.datetime.fromisoformat(text)),allowed)
 def test_stale_gaming_and_persistence(self):
  t=[0];p=Policy(clock=lambda:t[0]);p.save(dict(DEFAULT,playingRate=1048576));self.assertEqual(p.rate(),1048576);p.mark_playing(False);self.assertEqual(p.rate(),0);t[0]=11;self.assertEqual(p.rate(),1048576)
  with contextlib.nullcontext(Path(__file__).parent/'test-evidence') as folder:
   path=Path(folder)/'schedule.json';p=Policy(path);p.save(dict(DEFAULT,rate=2097152));self.assertEqual(Policy(path).value['rate'],2097152);path.write_text('{bad');self.assertFalse(Policy(path).value['enabled'])
 def test_rate_and_cancel(self):
  t=[0.];sleep=lambda value:t.__setitem__(0,t[0]+value);lim=RateLimiter(lambda:1048576,lambda:t[0],sleep);lim.charge(1048576);self.assertAlmostEqual(t[0],.75,places=5)
  with self.assertRaises(InterruptedError):lim.charge(1048576,lambda:True)
 def test_invalid(self):
  for update in [{'days':[True]},{'start':1440},{'playingRate':-1},{'enabled':True,'end':1320}]:
   with self.assertRaises(ValueError):validate(dict(DEFAULT,**update))
  ast.parse(((Path(__file__).resolve().parent.parent.parent/'worker')/'worker.py').read_text(encoding='utf8'))
if __name__=='__main__':unittest.main()
