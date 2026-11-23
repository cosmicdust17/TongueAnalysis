"""Persist one reader-facing report for the app and PDF; retain raw results separately."""
import re
from datetime import timedelta
from app.services.annotations import FEATURES

NOTICE = '本报告用于健康信息参考，不能替代面诊。如不适持续或加重，请及时就医。'
PRESENTATION_VERSION = 4

def clean(text):
    text = str(text or '')
    text = re.sub(r'(?:本次已保存的.*?检测结果[：:]|模型返回的舌象观察为[：:])', '', text)
    return re.sub(r'[^。！？\n]*(?:Qwen|YOLO|模型|待复核|联调|模板|冲突|生成时快照)[^。！？\n]*[。！？]?', '', text, flags=re.I).strip()

def plain_reading(quote):
    compact = re.sub(r'\s+', '', quote)
    # These are source-specific paraphrases, preserving the original conditional clauses.
    if '舌面上所附着的苔垢呈现白色' in compact:
        return '白苔是舌面呈白色的覆盖物。薄白苔下仍能看见舌体，厚白苔则会遮住舌体。'
    elif '苔薄白而润' in compact:
        return '薄而白、表面湿润的舌苔可见于正常舌象，也可见于外感初起、病情较轻或身体偏寒等情况。薄白苔偏滑或偏干时，教材分别列有其他解释。'
    elif '口干，但欲漱水不欲咽' in compact:
        return '这段教材讨论的是同时出现的几项表现：口干而只想漱口却不想咽水、舌色青紫和脉象涩滞。教材将这一组表现与中医所说的血瘀联系起来。'
    elif '口腔对舌象的影响' in compact:
        return '缺牙可能使同侧舌苔偏厚，镶牙或牙床不整齐可能在舌缘留下压痕。睡眠时张口呼吸也可能让舌苔变厚、变干，这些变化可以来自口腔或呼吸习惯。'
    elif '舌苔和舌质均出现异常' in compact:
        return '教材将舌体颜色与舌苔颜色、润燥合在一起观察。例如，舌色偏红、舌苔发黄且干燥构成一组表现，适用条件是这些特征同时出现。'


def reading(item):
    quote = str(item.get('text') or '').strip()
    explanation = plain_reading(quote)
    if not explanation:
        return None
    loc = item.get('location') if isinstance(item.get('location'),dict) else {}
    source = item.get('source_title') or item.get('title') or '来源未标明'
    parts=[source]
    if loc.get('chapter'): parts.append(loc['chapter'])
    reviewed = item.get('source_review_status')=='approved' or item.get('ocr_status')=='approved'
    if reviewed and loc.get('printed_page') is not None: parts.append('印刷第'+str(loc['printed_page'])+'页')
    elif loc.get('pdf_page') is not None: parts.append('PDF 第'+str(loc['pdf_page'])+'页')
    if reviewed and loc.get('paragraph') is not None: parts.append('第'+str(loc['paragraph'])+'段')
    if len(parts)==1 and isinstance(item.get('citation'),str) and not item['citation'].lstrip().startswith('{'):
        parts.append(clean(item['citation']))
    return {'explanation':explanation,'quote':quote,'reference':' · '.join(filter(None,parts)),
            'chunk_id':item.get('chunk_id') or item.get('entity_id')}

def advice(symptoms, profile, observed):
    age=profile.get('age'); sleep=bool(re.search('入睡困难|失眠|睡眠浅|睡眠较浅|睡不好|睡眠不佳|难入睡|睡不着|早醒|多梦',symptoms)); dry=bool(re.search('口干|口渴|咽干',symptoms))
    fatigue=bool(re.search('乏力|疲|没力|无力',symptoms)); stomach=bool(re.search('腹胀|胃|食欲|消化',symptoms))
    items=[]
    if sleep:
        items.append({'category':'作息','text':'固定每天的起床时间，连续一周记录上床时间和大致入睡时间；如果睡前仍在看手机，试着在睡前30分钟放下手机。'})
    elif fatigue:
        items.append({'category':'作息','text':'针对这次提到的乏力，连续一周在上午和下午各记录一次精神状态；如果白天需要休息，可在午后安排10至20分钟安静休息。'})
    else:
        items.append({'category':'作息','text':'如果近来作息时间变化较大，先选定一个可坚持的起床时间，连续7天记录睡眠和身体感受，观察自述不适是否变化。'})
    if dry:
        items.append({'category':'饮食','text':'针对口干，如果医生没有要求限制饮水，可在白天口渴时分次小口喝水，连续3天记录口干出现的时段；如果常喝甜饮料，可先将其中一杯换成白水。'})
    elif stomach:
        items.append({'category':'饮食','text':'针对胃口或腹部不适，连续一周记录每餐时间、食量及餐后感受；如果常一次吃得很饱，试着每餐少盛一些，慢慢吃，观察是否更舒适。'})
    elif re.search('白苔|苔白|黄苔|苔黄', observed):
        items.append({'category':'饮食','text':'如果想对照舌苔颜色的变化，连续3天在早餐前用相同光线拍照。若前一晚吃了容易染色的食物，可一并记下，方便比较。'})
    else:
        items.append({'category':'饮食','text':'如果不适常在进食后出现，连续3天记录食物、进餐时间和不适时间，先观察是否存在重复关联，避免仅凭舌色自行忌口。'})
    gentle = fatigue or (isinstance(age,int) and age>=65)
    items.append({'category':'锻炼','text':('如果身体允许，可在白天精神较好时慢走5至10分钟，每周3次，感觉疲倦就休息，不勉强完成。' if gentle else '如果平时活动较少且身体允许，可在饭后休息30分钟后慢走10至15分钟，每周3至5次；如有不适立即停止。')})
    return items


def tidy_observation(observation):
    observation = observation.removesuffix('本次未检出裂纹特征，这不代表可以排除裂纹。')
    if observation == '本次未检出可标注的舌象特征；仅凭这张照片，不能确认这些特征是否存在。':
        return '本张舌照未见可明确描述的舌象特征。'
    observation = re.sub(r'^观察舌象[，：:。]\s*', '', observation)
    fine_fissure = re.search(r'(?:可见|有)细(?:微)?裂纹', observation)
    seen = set()
    sentences = []
    for sentence in re.split(r'[。！？]+', observation):
        clauses = []
        for clause in re.split(r'[，、；]', sentence):
            clause = clause.strip()
            if not clause or clause in seen:
                continue
            if fine_fissure and re.fullmatch(r'但?(?:无|未见)明显裂纹|裂纹非主要表现', clause):
                continue
            clauses.append(clause)
            seen.add(clause)
        if clauses:
            sentences.append('，'.join(clauses) + '。')
    return ''.join(sentences)


def analysis_text(observation, evidence):
    # Textbook descriptions apply to visible features, not symptom matches alone.
    observation = tidy_observation(observation)
    if re.search(r'(?:白苔|苔白|苔薄白)', observation) and not re.search(r'(?:未见|未观察到|无明显|无|没有)(?:明确)?白苔', observation):
        for entry in evidence:
            quote = re.sub(r'\s+', '', entry['quote'])
            if '舌面上所附着的苔垢呈现白色' in quote:
                return f"{observation}\n教材按白色舌苔对舌体的遮盖程度区分厚薄，薄白苔下仍可见舌体[{entry['number']}]。"
        for entry in evidence:
            if '苔薄白而润' in re.sub(r'\s+', '', entry['quote']):
                return f"{observation}\n教材描述白苔时，还会区分苔的厚薄，以及表面偏润、偏滑或偏干[{entry['number']}]。"
    return observation


def merge_saved_presentation(previous):
    """Upgrade the layout using the saved observations, identity and advice."""
    view = dict(previous)
    evidence = [dict(item, explanation=plain_reading(item['quote']) or item['explanation']) for item in view['evidence']]
    observation = view.pop('observation', None) or view.get('analysis', '').split('\n', 1)[0]
    view.pop('self_report', None)
    view.pop('interpretation', None)
    observation = tidy_observation(observation)
    return {**view, 'version': PRESENTATION_VERSION, 'analysis': analysis_text(observation, evidence),
            'brief': observation if len(observation) <= 65 else observation[:64] + '…', 'evidence': evidence}


def compose(content, symptoms, duration, user_id, profile, created_at, evidence):
    annotations=content.get('annotations') or {}; boxes=annotations.get('detections',[])
    raw=clean(content.get('summary',''))
    raw = re.split(r'(?:用户自述|症状自述|教材解释)[：:]?', raw, maxsplit=1)[0]
    raw = re.sub(r'^\s*(?:舌照|舌象|图像|照片)观察\s*[：:]\s*', '', raw)
    sentences=[s.strip() for s in re.split(r'(?<=[。！？])|\n',raw) if s.strip()]
    observations=[]
    for sentence in sentences:
        sentence=re.split(r'，(?:提示|说明|可能为|可能伴有|属)|，?属于',sentence)[0]
        sentence = re.split(r'[，；]?症状与舌象结合|[，；]?结合(?:用户|自述|症状)', sentence)[0]
        if re.search('舌|苔|裂纹|齿痕|看不清|不清晰',sentence) and not re.search('自述|您|教材|书中|证候|病因|病机|阴虚|阳虚|血瘀|痰湿|主.*证',sentence):
            observations.append(sentence if sentence.endswith(('。','！','？')) else sentence+'。')
    if observations:
        observed=''.join(observations)
        observed=re.sub('(?:没有|无)裂纹','本张照片未观察到明确裂纹',observed)
    elif boxes:
        observed='舌照中可见'+ '、'.join(dict.fromkeys(b['name'] for b in boxes))+'的表现。'
    else:
        observed='本张舌照未见可明确描述的舌象特征。'
    interpretations = []
    for item in evidence:
        entry = reading(item) if not item.get('is_demo') else None
        if entry:
            interpretations.append({'number': len(interpretations) + 1, **entry})
    if content.get('is_demo'):
        observed='示例舌照仅供体验报告阅读流程，不用于个人健康判断。'
    observed = tidy_observation(observed)
    labels=[]
    for b in boxes:
        if b['name'] not in [x['name'] for x in labels]:
            description=FEATURES.get(b.get('class_name'),{}).get('description',b.get('description',''))
            labels.append({'name':b['name'],'description':description.replace('模型标注的','标注的')})
    return {'version':PRESENTATION_VERSION,'title':'舌象综合分析报告',
        'identity':{'user_id':user_id,'age':profile.get('age') if profile.get('age') is not None else '未填写','gender':profile.get('gender') or '未填写',
                    'report_date':(created_at+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')},
        'symptoms_text':symptoms,'duration':duration or '未填写','analysis':analysis_text(observed, interpretations),
        'brief':observed if len(observed)<=65 else observed[:64]+'…',
        'advice_items':advice(symptoms,profile,observed),'evidence':interpretations,'annotation_labels':labels,'notice':NOTICE}
