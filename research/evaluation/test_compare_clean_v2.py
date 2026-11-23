"""Matching edge cases that can otherwise change the fixed-threshold recall."""
from types import SimpleNamespace
import unittest

import numpy as np
import torch
from ultralytics.engine.validator import BaseValidator

from compare_clean_v2 import greedy_pairs


class FissureMatchingTests(unittest.TestCase):
    def test_one_gt_cannot_produce_two_true_positives(self):
        iou = np.array([[0.9, 0.8]])
        pairs = greedy_pairs(iou)
        self.assertEqual(pairs.tolist(), [[0, 0]])
        # The low-score higher-IoU candidate is removed before matching at a fixed threshold.
        self.assertEqual(greedy_pairs(iou[:, [1]]).tolist(), [[0, 0]])

    def test_no_detections_no_labels_and_boundary(self):
        for matrix in (np.empty((2, 0)), np.empty((0, 3)), np.array([[0.4999]])):
            self.assertEqual(len(greedy_pairs(matrix)), 0)
        self.assertEqual(greedy_pairs(np.array([[0.5]])).tolist(), [[0, 0]])

    def test_pair_assignments_agree_with_installed_validator(self):
        iou = np.array([[0.9, 0.8, 0.0], [0.7, 0.0, 0.75]], dtype=np.float32)
        reference = SimpleNamespace(iouv=torch.tensor([0.5]))
        correct = BaseValidator.match_predictions(reference, torch.full((3,), 2), torch.full((2,), 2), torch.tensor(iou))
        self.assertEqual(set(greedy_pairs(iou)[:, 1]), set(torch.where(correct[:, 0])[0].tolist()))


if __name__ == '__main__':
    unittest.main()
