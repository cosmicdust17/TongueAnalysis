"""Local-only text extraction. Console output is deliberately bounded."""
import re
from pathlib import Path
from .io_utils import digest, file_hash, read_json, write_json, write_rows


def page_lines(page, ocr_engine=None):
    import numpy as np
    blocks = page.get_text("dict")["blocks"]
    lines = []
    for block in blocks:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                lines.append({"text": text, "bbox": list(line["bbox"]), "confidence": None})
    # Only pages with missing/unusable text get OCR. Never OCR the whole book by default.
    usable = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", "".join(v["text"] for v in lines))
    if len(usable) >= 30:
        return lines, "text_layer"
    if ocr_engine is None:
        return [], "needs_ocr"
    pix = page.get_pixmap(matrix=__import__("pymupdf").Matrix(2, 2), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    result, _ = ocr_engine(image)
    lines = []
    for box, text, confidence in result or []:
        xs, ys = zip(*box)
        lines.append({"text": text, "bbox": [min(xs)/2, min(ys)/2, max(xs)/2, max(ys)/2], "confidence": confidence})
    return sorted(lines, key=lambda x: (round(x["bbox"][1] / 5), x["bbox"][0])), "local_ocr"


def inspect_pdf(pdf, out, pages, ocr=False):
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    engine = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=2) if ocr else None
    write_json(out / "inspection.json", {"pdf": str(pdf), "pages": len(doc), "bookmarks": doc.get_toc(), "metadata": doc.metadata})
    for number in pages:
        lines, method = page_lines(doc[number-1], engine)
        write_json(out / f"page-{number:03}.json", {"pdf_page": number, "method": method, "lines": lines})
        (out / f"page-{number:03}.txt").write_text("\n".join(v["text"] for v in lines), encoding="utf-8")
        doc[number-1].get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(str(out / f"page-{number:03}.png"))
        print(f"PDF {number}: {method}, lines={len(lines)}")


HEADING = re.compile(r"^(第[一二三四五六七八九十百]+[章节]|[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])")


def paragraphs(lines, width, height):
    """Conservative layout heuristic; physical block locator is kept, printed paragraph stays unknown."""
    body = [v for v in lines if height * .08 < v["bbox"][1] < height * .95]
    groups, group = [], []
    for line in body:
        prev = group[-1] if group else None
        gap = line["bbox"][1] - prev["bbox"][3] if prev else 0
        heading = bool(HEADING.match(line["text"])) and len(line["text"]) < 55
        indent = prev and line["bbox"][0] - prev["bbox"][0] > 12
        if group and (heading or gap > 12 or indent or (len(group[-1]["text"]) < 50 and HEADING.match(group[-1]["text"]))):
            groups.append(group)
            group = []
        group.append(line)
    if group:
        groups.append(group)
    return groups


def extract(pdf, plan_path, out):
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    plan = read_json(plan_path)
    if not plan.get("bibliography_confirmed"):
        raise ValueError("Confirm bibliography from copyright page in plan first")
    for field in ("source_title", "edition", "publisher", "copyright_pdf_page"):
        if not plan.get(field):
            raise ValueError(f"Missing confirmed bibliography: {field}")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    doc, sha = pymupdf.open(pdf), file_hash(pdf)
    cache_valid = (out / 'manifest.json').exists() and read_json(out / 'manifest.json').get('pdf_sha256') == sha
    engine = None
    chunks, anomalies, processed, selected = [], [], {}, set()
    for section in plan["sections"]:
        start, end = section["pdf_start"], section["pdf_end"]
        if not 1 <= start <= end <= len(doc):
            raise ValueError("Invalid selected page range")
        for number in range(start, end + 1):
            if number in selected:
                raise ValueError("Overlapping sections require explicit non-overlapping page selection")
            selected.add(number)
            page = doc[number-1]
            cached_page = out / 'pages' / f'{number:03}.json'
            if cache_valid and cached_page.exists():
                cached = read_json(cached_page)
                lines, method = cached['lines'], cached['method']
            else:
                lines, method = page_lines(page)
            if method == "needs_ocr":
                if engine is None:
                    engine = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=2)
                lines, method = page_lines(page, engine)
            write_json(out / "pages" / f"{number:03}.json", {"pdf_page": number, "method": method, "lines": lines})
            raw = "\n".join(v["text"] for v in lines)
            raw_path = out / "raw" / f"{number:03}.txt"
            raw_path.parent.mkdir(exist_ok=True)
            raw_path.write_text(raw, encoding="utf-8")
            bounds = plan.get('page_bounds', {}).get(str(number), {})
            lines = [v for v in lines if bounds.get('y_start', 0) <= v['bbox'][1] < bounds.get('y_end', page.rect.height)]
            processed[str(number)] = method
            if not lines:
                anomalies.append({"pdf_page": number, "issue": "empty_after_ocr"})
            if any(v["confidence"] is not None and v["confidence"] < .85 for v in lines):
                anomalies.append({"pdf_page": number, "issue": "low_ocr_confidence_review_required"})
            subsection = section["chapter"]
            groups = []
            for paragraph_no, paragraph in enumerate(paragraphs(lines, page.rect.width, page.rect.height), 1):
                # Bound fragment length without dropping long paragraphs at the embedding tokenizer limit.
                part, size = [], 0
                for line in paragraph:
                    if part and size + len(line['text']) > 350:
                        groups.append((paragraph_no, part))
                        part, size = [], 0
                    part.append(line)
                    size += len(line['text'])
                if part:
                    groups.append((paragraph_no, part))
            for i, (paragraph_no, group) in enumerate(groups, 1):
                text = "\n".join(v["text"] for v in group)
                if HEADING.match(group[0]["text"]) and len(group[0]["text"]) < 55:
                    subsection = section["chapter"] + " / " + group[0]["text"]
                box = [min(v["bbox"][0] for v in group), min(v["bbox"][1] for v in group), max(v["bbox"][2] for v in group), max(v["bbox"][3] for v in group)]
                location = {"chapter": subsection, "pdf_page": number,
                            "printed_page": plan.get("printed_pages", {}).get(str(number)),
                            "paragraph": None, "block_on_page": paragraph_no, "fragment_on_page": i, "bbox": box,
                            "paragraph_status": "layout_heuristic_requires_review"}
                chunks.append({"chunk_id": "ch_" + digest([sha, number, i, text])[:24], "text": text,
                               "source_title": plan["source_title"], "edition": plan["edition"],
                               "publisher": plan["publisher"], "pdf_sha256": sha,
                               "location": location, "extraction_method": method, "is_demo": False})
        print(f"Selected PDF {start}-{end}: {section['chapter']}")
    write_rows(out / "chunks.jsonl", chunks)
    write_json(out / "manifest.json", {"pdf_sha256": sha, "plan": plan, "page_methods": processed,
                                       "chunk_count": len(chunks), "corpus_hash": digest(chunks), "anomalies": anomalies})
    print(f"chunks={len(chunks)}, pages={len(selected)}, anomalies={len(anomalies)}")
    for chunk in chunks[:2]:
        print(chunk["chunk_id"], chunk["location"]["pdf_page"], chunk["text"][:60])
