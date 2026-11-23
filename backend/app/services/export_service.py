from io import BytesIO
from pathlib import Path
from PIL import Image
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Flowable, Table, TableStyle, LongTable, KeepTogether
from reportlab.lib.utils import ImageReader

pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT = 'STSong-Light'
if Path('C:/Windows/Fonts/simhei.ttf').is_file():
    pdfmetrics.registerFont(TTFont('ReportChinese', 'C:/Windows/Fonts/simhei.ttf'))
    FONT = 'ReportChinese'


class AnnotatedPhoto(Flowable):
    def __init__(self, path, annotations):
        super().__init__()
        self.path, self.boxes = path, annotations.get('detections', [])
        with Image.open(path) as image:
            width, height = image.size
        scale = min(410 / width, 240 / height)
        self.width, self.height = width * scale, height * scale

    def draw(self):
        c = self.canv
        c.drawImage(ImageReader(self.path), 0, 0, self.width, self.height)
        labels = []
        for box in self.boxes:
            x1, y1, x2, y2 = box['xyxy']
            x, y = x1 * self.width, (1 - y2) * self.height
            c.setStrokeColor(colors.white)
            c.setLineWidth(2.5)
            c.rect(x, y, (x2-x1)*self.width, (y2-y1)*self.height)
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.8)
            c.rect(x, y, (x2-x1)*self.width, (y2-y1)*self.height)
            text = box['name']
            tag_width = pdfmetrics.stringWidth(text, FONT, 11) + 8
            tx = min(x, self.width - tag_width)
            ty = max(0, min(self.height - 16, (1-y1)*self.height - 16))
            while any(abs(ty-py) < 16 and tx < px+pw and tx+tag_width > px for px,py,pw in labels) and ty >= 16:
                ty -= 16
            labels.append((tx,ty,tag_width))
            c.setFillColor(colors.white)
            c.rect(tx, ty, tag_width, 16, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.setFont(FONT, 11)
            c.drawString(tx+4, ty+4, text)

def render_report(report, image_path=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, title='舌象综合分析报告', author='舌象智能分析系统',
                            leftMargin=40, rightMargin=40, topMargin=32, bottomMargin=32)
    body = ParagraphStyle('body', fontName=FONT, fontSize=10.5, leading=17, wordWrap='CJK', textColor=colors.black)
    small = ParagraphStyle('reference', parent=body, fontSize=9, leading=15)
    title = ParagraphStyle('title', parent=body, fontSize=20, leading=30, alignment=1, spaceAfter=15)
    def para(text, style=body):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),style)
    c=report.content; view=c['presentation']; identity=view['identity']
    story=[para(view['title'],title)]
    header=Table([[para('用户 ID'),para(identity['user_id']),para('年龄'),para(identity['age'])],
                  [para('报告日期'),para(identity['report_date']),para('性别'),para(identity['gender'])]],colWidths=[65,300,55,95])
    style=[('GRID',(0,0),(-1,-1),.45,colors.HexColor('#d6d6d6')),('VALIGN',(0,0),(-1,-1),'TOP'),
           ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]
    header.setStyle(TableStyle(style));story.extend([header,Spacer(1,14)])
    rows=[]
    def row(label,text): rows.append([para(label),para(text)])
    if image_path and Path(image_path).is_file():
        photo=AnnotatedPhoto(image_path,c.get('annotations',{}));rows.append([para('本次舌照'),photo])
    else:row('本次舌照','图片暂不可用')
    if not view['annotation_labels']:row('标注说明','本次未检出可标注的舌象特征')
    for label in view['annotation_labels']:row('标注说明',label['name']+'：'+label['description'])
    row('症状自述', f"{view['symptoms_text']}\n持续时间：{view['duration']}")
    row('舌象分析', view['analysis'])
    for item in view['advice_items']:row('日常建议 · '+item['category'],item['text'])
    if not view['evidence']:row('知识依据','暂缺可直接对应的教材依据。')
    for item in view['evidence']:
        # Reflow the source excerpt to the cell width rather than the textbook's line lengths.
        quote = item['quote'].replace('\n', '')
        row(f"知识依据 [{item['number']}]", f"白话解读：{item['explanation']}\n教材原文：{quote}")
    table=LongTable(rows,colWidths=[80,435],splitByRow=1,splitInRow=1)
    table.setStyle(TableStyle(style))
    story.append(table)
    references = [para('参考', small)] if view['evidence'] else []
    references.extend(para(f"[{item['number']}] {item['reference']}", small) for item in view['evidence'])
    story.append(KeepTogether([Spacer(1, 12), *references, Spacer(1, 8), para(view['notice'], small)]))
    doc.build(story)
    return buffer.getvalue()
