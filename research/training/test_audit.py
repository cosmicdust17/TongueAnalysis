"""Small synthetic checks: parsing, leakage and missing-label safety."""
import json
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from PIL import Image
from audit_data import audit, parse_label
from prepare_data import prepare

class AuditTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(parse_label('20 0.5 0.5 1 1')[1], [])
        self.assertEqual(parse_label('')[0], [])
        for text in ['21 .5 .5 .1 .1', '1 nan .5 .1 .1', '1 .01 .5 .2 .2',
                     '1 .5 .5 0 .1', '1 .5 .5 .1', '1 .5 .5 .1 .1\n1 .5 .5 .1 .1']:
            self.assertTrue(parse_label(text)[1], text)

    def test_leak_and_missing_are_blockers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source'
            data = source/'example-txt'
            for i,split in enumerate(('train','val','test')):
                (data/split/'images').mkdir(parents=True)
                (data/split/'labels').mkdir()
                Image.new('RGB',(20,20),'red').save(data/split/'images'/'same.png')
                if split != 'test':
                    (data/split/'labels'/'same.txt').write_text('0 .5 .5 .5 .5')
            (source/'classes.txt').write_text('\n'.join(f'class_{i}' for i in range(21)))
            result = audit(source, root/'output')
            self.assertIn('Cross-split exact image leakage', result['blockers'])
            self.assertEqual(result['summary']['test']['label_status'], {'missing':1})
            self.assertTrue(result['duplicates'])
            with self.assertRaisesRegex(ValueError, 'blocked formal training'):
                prepare(Namespace(audit=root/'output', classes=None, smoke=False))

if __name__ == '__main__': unittest.main()
