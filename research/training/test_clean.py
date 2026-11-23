import json
from pathlib import Path
import tempfile
import unittest
import yaml
from clean_dataset import agreement
from common import digest, load_config, write_json

class CleanTests(unittest.TestCase):
    def test_class_preserving_agreement(self):
        a=[[2,.5,.5,.5,.5],[9,.5,.5,.5,.5]]
        self.assertTrue(agreement(a,list(reversed(a)),(640,640))[0])
        self.assertFalse(agreement(a,[[3,.5,.5,.5,.5],[9,.5,.5,.5,.5]],(640,640))[0])
        self.assertFalse(agreement(a,a[:1],(640,640))[0])
        self.assertTrue(agreement(a,[[2,.500001,.5,.5,.5],[9,.5,.5,.5,.5]],(640,640))[0])
        self.assertFalse(agreement(a,[[2,.51,.5,.5,.5],[9,.5,.5,.5,.5]],(640,640))[0])

    def test_audited_class_count_and_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'data.yaml'
            for n in (7,21):
                config=dict(nc=n,names={i:f'class_{i}' for i in range(n)})
                p.write_text(yaml.safe_dump(config))
                write_json(p.with_suffix('.provenance.json'),dict(config_sha256=digest(p),nc=n,names=config['names']))
                self.assertEqual(load_config(p)[0]['nc'],n)
            p.write_text(p.read_text()+'# edited\n')
            with self.assertRaisesRegex(ValueError,'changed after preparation'):load_config(p)

if __name__=='__main__':unittest.main()
