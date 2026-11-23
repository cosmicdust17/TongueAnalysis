import unittest
from apply_fissure_review import decision, draft_box, POLICY, read

class HumanReviewTests(unittest.TestCase):
    def test_user_totals_and_negative_predictions(self):
        policy=read(POLICY)
        self.assertEqual(len(policy['present_numbers']),25)
        self.assertEqual(set(policy['absent_numbers']),{16,22,28})
        def evidence(pred):return dict(predictions=pred,source_fissure_count=0,coco_fissure_count=0,clean_fissure_count=0)
        self.assertEqual(decision(16,evidence([{}]),policy)['model_assessment'],'false_positive')
        self.assertEqual(decision(28,evidence([]),policy)['model_assessment'],'correct_no_detection')
        self.assertEqual(decision(27,evidence([]),policy)['model_assessment'],'false_negative_at_recorded_threshold')
        result=decision(24,evidence([{}]),policy)
        self.assertEqual(result['annotation_issue'],'missing_fissure_annotation')
        self.assertEqual(result['model_assessment'],'partial_localization_user_confirmed')

    def test_draft_is_unapproved_and_bounds_checked(self):
        draft=draft_box([.1,.2,.4,.6],100,200)
        self.assertEqual(draft['xyxy_pixels'],[10,40,40,120])
        self.assertEqual(draft['approval'],'pending_user_confirmation')
        self.assertIsNone(draft['model_score'])
        for box in [[-.1,.2,.4,.6],[.4,.2,.1,.6],[.1,.2,.4,1.1]]:
            with self.assertRaises(ValueError):draft_box(box,100,200)

if __name__=='__main__':unittest.main()
