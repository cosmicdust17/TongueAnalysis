"""Conservative page quarantine until a named reviewer clears each affected chunk."""
import os
from pathlib import Path
from .io_utils import digest, read_json

FLAGGED_PAGES = {57, 64}


def quality(chunk):
    flagged = not chunk.get('is_demo') and chunk.get('location', {}).get('pdf_page') in FLAGGED_PAGES
    status = 'pending_review' if flagged else 'not_flagged'
    reviewer = reviewed_at = None
    review_file = os.getenv('RETRIEVAL_OCR_REVIEW_FILE')
    source_review = 'unreviewed'
    if review_file and Path(review_file).exists():
        record = read_json(review_file).get(chunk['chunk_id'], {})
        if (record.get('status') == 'approved' and record.get('source_hash') == digest(chunk)
                and record.get('reviewer') and record.get('reviewed_at')):
            status, reviewer, reviewed_at = 'approved', record['reviewer'], record['reviewed_at']
            source_review = 'approved'
    return {'retrieval_eligible': not flagged or status == 'approved', 'ocr_status': status,
            'source_review_status': source_review,
            'ocr_reviewer': reviewer, 'ocr_reviewed_at': reviewed_at,
            'ocr_review_reason': 'PDF page flagged for low-confidence OCR; page quarantined conservatively' if flagged else None}
