from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings
from time import perf_counter
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from PIL import Image, ImageOps
from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user
from app.models import User, StoredFile
from app.services.common import audit

router = APIRouter(prefix='/uploads', tags=['文件'])

@router.post('', status_code=201)
async def upload(file: UploadFile = File(...), purpose: str = Query(default='image', pattern='^(image|document)$'), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if purpose == 'document' and user.role != 'knowledge_admin':
        raise HTTPException(403, '仅知识库管理员可以上传文档')
    maximum = settings().upload_max_mb * 1024 * 1024
    data = bytearray()
    try:
        while chunk := await file.read(64 * 1024):
            data.extend(chunk)
            if len(data) > maximum:
                raise HTTPException(413, '文件超过大小限制')
    finally:
        await file.close()
    if not data:
        raise HTTPException(400, '文件为空')
    filename = (file.filename or 'upload').replace('\\', '/').split('/')[-1][:200]
    if purpose == 'image':
        preprocessing_started = perf_counter()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 24_000_000 or min(image.size) < 64 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError('Unsupported image')
                    normalized = ImageOps.exif_transpose(image).convert('RGB')
                    normalized.thumbnail((2048, 2048))
                    buffer = BytesIO()
                    normalized.save(buffer, format='JPEG', quality=92)
                    data = buffer.getvalue()
            suffix, mime = '.jpg', 'image/jpeg'
        except Exception:
            raise HTTPException(400, '请选择有效的 JPEG、PNG 或 WebP 静态图片（最短边至少64像素，最多2400万像素）')
        preprocessing_seconds = perf_counter()-preprocessing_started
    else:
        preprocessing_seconds = 0
        suffix = Path(filename).suffix.lower()
        if suffix == '.pdf' and bytes(data[:5]) == b'%PDF-':
            mime = 'application/pdf'
        elif suffix == '.txt':
            try:
                bytes(data).decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(400, 'TXT文档需要使用UTF-8编码')
            mime = 'text/plain; charset=utf-8'
        else:
            raise HTTPException(400, '来源文档支持PDF或UTF-8 TXT；当前版本需手动整理实体关系')
    directory = Path(settings().storage_path).resolve() / ('uploads' if purpose == 'image' else 'documents')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (uuid4().hex + suffix)
    target.write_bytes(data)
    item = StoredFile(owner_id=user.id, original_name=filename, path=str(target), content_type=mime, purpose=purpose, size=len(data))
    try:
        db.add(item)
        audit(db, user, '上传舌象图片' if purpose == 'image' else '上传来源文档')
        db.commit()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {'id': item.id, 'name': item.original_name, 'size': item.size, 'url': f'/api/v1/uploads/{item.id}/content',
            'preprocess_seconds': preprocessing_seconds}

@router.get('/{file_id}/content')
def content(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(StoredFile, file_id)
    if not item or (item.owner_id != user.id and not (item.purpose == 'document' and user.role == 'knowledge_admin')):
        raise HTTPException(404, '文件不存在')
    if not Path(item.path).is_file():
        raise HTTPException(404, '文件已不可用')
    return FileResponse(item.path, media_type=item.content_type, filename=item.original_name,
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
