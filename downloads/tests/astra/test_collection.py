import sys,unittest
from pathlib import Path
sys.path.insert(0,str((Path(__file__).resolve().parent.parent.parent/'worker')))
from collections_preview import Collections,public_url
class Tests(unittest.TestCase):
 def test_bounds_and_private(self):
  calls=[];c=Collections(lambda u,o:{'entries':[{'url':'https://example.org/'+str(i),'title':'Video'} for i in range(105)]},lambda *a,**k:calls.append(k) or 'job')
  s=c.inspect('https://example.org/list');self.assertEqual(len(s['entries']),100);self.assertTrue(s['truncated']);self.assertNotIn('url',s['entries'][0])
  for u in ['file:///a','http://127.0.0.1','https://localhost','https://u:p@example.org']:
   with self.assertRaises(ValueError):public_url(u)
 def test_replay_partial_expiry(self):
  count=[0];clock=[0]
  def job(*a,**k):
   count[0]+=1
   if count[0]==2:raise ValueError('Full')
   return 'job'+str(count[0])
  c=Collections(lambda u,o:{'entries':[{'url':'https://example.org/a'},{'url':'https://example.org/b'}]},job,lambda:clock[0]);s=c.inspect('https://example.org/list')
  out=c.submit(s['id'],['0','1']);self.assertEqual(len(out['accepted']),1);self.assertTrue(out['error'])
  out=c.submit(s['id'],['0']);self.assertEqual(count[0],2);self.assertEqual(out['accepted'][0]['jobId'],'job1')
  with self.assertRaises(ValueError):c.submit(s['id'],['0','0'])
  with self.assertRaises(ValueError):c.submit(s['id'],['wrong'])
  clock[0]=301
  with self.assertRaises(ValueError):c.submit(s['id'],['0'])
 def test_invalid_entries(self):
  c=Collections(lambda u,o:{'entries':[None,{'url':'file:///bad'},{'url':'https://example.org/live','is_live':True},{'url':'https://example.org/good','filesize':True}]},lambda *a,**k:None)
  s=c.inspect('https://example.org/list');self.assertEqual(len(s['entries']),1);self.assertIsNone(s['entries'][0]['bytes'])
if __name__=='__main__':unittest.main()
