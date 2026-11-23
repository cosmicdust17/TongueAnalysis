"""Ensure numeric jitter is not reported as an adjudicated class conflict."""
import unittest
from review_data import compare

class ReviewTests(unittest.TestCase):
    def test_numeric_and_class_changes(self):
        a=[[19,.5,.5,.2,.2]]
        self.assertEqual(compare(a,a,(640,640))['classification'],'exact_annotations')
        self.assertEqual(compare(a,[[19,.500001,.5,.2,.2]],(640,640))['classification'],'numeric_difference_within_1px')
        changed=compare(a,[[18,.5,.5,.2,.2]],(640,640))
        self.assertEqual(changed['classification'],'class_id_difference')
        self.assertEqual(changed['matched'][0]['iou'],1)

    def test_missing_and_multiple_boxes(self):
        a=[[18,.2,.2,.1,.1],[19,.8,.8,.1,.1]]
        self.assertEqual(compare(a,list(reversed(a)),(640,640))['classification'],'exact_annotations')
        self.assertEqual(compare(a,a[:1],(640,640))['classification'],'unmatched_instances')
        result=compare(a,[[18,.3,.2,.1,.1]],(640,640))
        self.assertTrue(result['unmatched_a'])
        same_geometry=[[18,.5,.5,.2,.2],[19,.5,.5,.2,.2]]
        self.assertEqual(compare(same_geometry,list(reversed(same_geometry)),(640,640))['classification'],'exact_annotations')

if __name__=='__main__':unittest.main()
