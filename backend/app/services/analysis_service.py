import asyncio
import logging
from time import perf_counter
from sqlalchemy import select, update
from app.core.database import SessionLocal
from app.models import Analysis, StoredFile, Report, Evidence, Alert, User, now
from app.integrations.inference.factory import model_adapter
from app.integrations.retrieval.retriever import retrieve_evidence
from app.integrations.generation.generator import build_report
from .common import audit
from .annotations import annotation_snapshot
from .report_presentation import compose

logger = logging.getLogger(__name__)

def recover_interrupted():
    # The included runner intentionally uses a single Uvicorn process.
    with SessionLocal() as db:
        rows = db.scalars(select(Analysis).where(Analysis.status == 'running')).all()
        for row in rows:
            row.status, row.progress = 'queued', 0
        if rows:
            audit(db, None, f'恢复 {len(rows)} 个中断分析任务', category='system')
        db.commit()

def process_one():
    with SessionLocal() as db:
        aid = db.scalar(select(Analysis.id).where(Analysis.status == 'queued').order_by(Analysis.created_at).limit(1))
        if not aid:
            return False
        claimed = db.execute(update(Analysis).where(Analysis.id == aid, Analysis.status == 'queued').values(status='running', progress=15, updated_at=now()))
        db.commit()
        if not claimed.rowcount:
            return True
        row = db.get(Analysis, aid)
        image = db.get(StoredFile, row.image_id)
        try:
            started = perf_counter()
            result = asyncio.run(model_adapter().analyze(image.path, row.symptoms))
            row.progress = 55
            db.commit()
            evidence = (result.fusion_result['evidence'] if 'qwen' in result.fusion_result
                        else retrieve_evidence(result, row.symptoms))
            annotations = annotation_snapshot(result.model_dump(), image.path, result.model_version)
            content = build_report(result, row.symptoms, row.duration, evidence, annotations)
            content['annotations'] = annotations
            user = db.get(User, row.user_id)
            content['presentation'] = compose(content, row.symptoms, row.duration, row.user_id, user.profile or {}, now(), evidence)
            content['inference_metrics']['analysis_seconds'] = perf_counter() - started
            report = db.scalar(select(Report).where(Report.analysis_id == aid))
            persistence_started = perf_counter()
            if not report:
                report = Report(analysis_id=aid, user_id=row.user_id, content=content, is_demo=content['is_demo'])
                db.add(report)
                db.flush()
                for item in evidence:
                    db.add(Evidence(report_id=report.id, graph_entity_id=item['entity_id'], snapshot=item))
            db.flush()
            report.content = {**content, 'inference_metrics': {**content['inference_metrics'],
                'report_flush_seconds': perf_counter()-persistence_started}}
            row.result = result.model_dump()
            row.status, row.progress, row.error = 'completed', 100, ''
            audit(db, None, '分析任务完成', category='system')
            db.commit()
        except Exception:
            db.rollback()
            logger.exception('Analysis task failed: %s', aid)
            row = db.get(Analysis, aid)
            row.status, row.error = 'failed', '分析处理失败，请检查模型或图谱服务后重试'
            db.add(Alert(service='analysis', message=f'分析任务 {aid} 处理失败'))
            audit(db, None, '分析任务失败', category='exception', status='failed')
            db.commit()
    return True
