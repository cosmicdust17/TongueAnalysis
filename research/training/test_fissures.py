import unittest
from review_fissures import overlaps

class NovelFissureTests(unittest.TestCase):
    def test_unlabelled_and_disjoint(self):
        self.assertEqual(overlaps([0,0,10,10],[]),(0,0))
        self.assertEqual(overlaps([20,20,30,30],[[2,0,0,10,10]]),(0,0))

    def test_small_box_inside_gt_is_not_novel(self):
        iou,coverage=overlaps([1,1,2,2],[[2,0,0,10,10]])
        self.assertLess(iou,.1)
        self.assertEqual(coverage,1)
        self.assertFalse(iou<.1 and coverage<.2)

if __name__=='__main__':unittest.main()
