"""Write final decision tables and human-readable delivery from completed re-audit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from clean_dataset import read_json, table
from common import ROOT, digest, write_json

def summarize(a):
    logs=a.logs.resolve();data=a.data.resolve();r=read_json(logs/'reaudit.json');build=read_json(logs/'build.json')
    m=read_json(logs/'clean_manifest.json');by_rel={x['original_relative']:x for x in m}
    exact=read_json(logs/'exact_group_decisions.json');near=read_json(logs/'remaining_near_review.json')
    table(logs/'exact_79_final.csv',[dict(group_id=g['group_id'],decision=g['decision'],
        retained_source=g['retained_source_path'] or '',retained_clean_copy=by_rel[g['retained_original']]['destination'] if g['retained_original'] else '',
        excluded_source_paths=json.dumps(g['removed_from_training'],ensure_ascii=False),
        quarantine_copies=json.dumps([x['destination'] for x in m if x['source_image'] in g['removed_from_training']],ensure_ascii=False),
        annotation_basis=g['annotation_basis'],evidence=g['evidence']) for g in exact if g['cross_split']])
    table(logs/'near_final_decisions.csv',[dict(group_id=p['group_id'],a_source=by_rel[p['a']]['source_image'],
        b_source=by_rel[p['b']]['source_image'],a_status=p['a_clean_status'],b_status=p['b_clean_status'],
        cross_split=p['cross_split'],both_in_clean=p['both_in_clean'],review_status=p['review_status'],
        decision=p['decision'],observation=p['observation'],evidence=p['evidence']) for p in near])
    identity=[(x['original_relative'],x['image_sha256'],x['destination_label_sha256']) for x in m if x['status']=='retained']
    fingerprint=hashlib.sha256(json.dumps(sorted(identity),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    weights=ROOT/'weights'/'yolo11n.pt'
    write_json(logs/'delivery.json',dict(selection_sha256=fingerprint,pretrained_sha256=digest(weights),
        pretrained_source='https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt',
        re_audit_sha256=digest(logs/'reaudit.json'),config_sha256=digest(data/'data.yaml'),training_started=False))
    rows=r['class_counts'];lookup={(x['split'],x['original_id']):x for x in rows}
    names={2:'红舌',3:'紫舌',7:'裂纹',8:'齿痕',9:'白苔',10:'黄苔',11:'黑苔'}
    lines=['# 第一版清洗数据副本交付','',
        '仅处理舌象图片。原始数据未改；本轮没有训练。项目及父级未找到AGENTS.md。', '',
        f"有效图片：train={r['split_images']['train']}、val={r['split_images']['val']}、test={r['split_images']['test']}，共{r['total_images']}张；隔离{r['quarantined_images']}张。",
        '保留原始split，不重分、不将测试图片转为训练图片。所有过滤后零框图片均隔离，没有未经确认的负样本。', '',
        '## 类别及统计', '',
        '保留原始拼音名；中文仅用于说明本轮目标范围，不推导疾病或未确认医学属性。', '',
        '| 原始ID | 新ID | 原始名称 | 目标 | train 图/框 | val 图/框 | test 图/框 |',
        '|---|---|---|---|---|---|---|']
    for old,new in build['original_to_new'].items():
        old=int(old);parts=[lookup[s,old] for s in ('train','val','test')]
        lines.append(f"| {old} | {new} | {parts[0]['name']} | {names[old]} | "+' | '.join(f"{x['images']}/{x['boxes']}" for x in parts)+' |')
    lines += ['', '依据：三份本地classes.txt、原TXT YAML及三份COCO JSON categories在这些ID上一致；每张有效图片还要求同split同名、文件SHA相同的COCO目标框集合与TXT一致（按类别一一匹配、最大边差<=1px）。不从COCO导入额外框，不取多份标注的并集。',
        '[全部21个原始类别的处理](class_mapping.csv) / [映射源文件及哈希](mapping_sources.json) / [逐图依据](clean_manifest.json)。19/20未交换；1、12–20号出现时整图隔离。0、4、5、6属于已知非本轮目标，只隔离其标注；剩余目标框必须非空。', '',
        '## 重复与待确认项', '',
        '79组跨集合精确重复：1组保留一份（exact_124，原val/images/tongue (434).jpg），78组整体隔离。包括54组同集合重复在内，全部133组均已处理。只有所有成员目标类集合相符且通过其他检查时，才按test、val、train优先级保留一份；不同类别或缺失/多余框不自动修补。',
        '[79组最终保留/隔离路径](exact_79_final.csv) / [133组完整标注依据](exact_group_decisions.json)。空保留路径表示整组隔离，并非遗漏；removed仅指移出有效训练/评估集合，原图和隔离副本均保留。', '',
        f"616对近重复中，211对跨集合。优先查看了2对test相关、6对val相关的原图，观察记录见visual_review.json；其余候选未伪称人工确认。全部跨集合候选端点按未解风险隔离，未按分数认定重复或删除原图。有效集跨集合候选剩余{r['active_unresolved_cross_split_near_pairs']}对，仍保留{r['active_same_split_near_pairs']}对同集合候选待确认。",
        '[全部616对最终状态](near_final_decisions.csv) / [完整剩余复核记录](remaining_near_review.json) / [隔离原因清单](quarantine.csv)。近重复筛查不穷尽；未知患者ID仍不能证明患者独立。', '',
        '## 独立复审', '',
        f"缺失标签={r['missing_labels']}；空标签={r['empty_labels']}；图像/类别/坐标错误={r['images_with_errors']}；跨集合精确重复=0；阻断项={len(r['blockers'])}。文件SHA和解码RGB哈希均重新计算；隔离图片及标签也验证了与来源哈希一致。",
        '[复审报告](reaudit.md) / [复审JSON](reaudit.json) / [各split逐类图数与框数](class_counts.csv)。黑苔测试仅3张、验证8张，类不平衡明显，不能据少量样本作稳定临床结论。', '',
        '## 文件与复现', '',
        f'有效YOLO副本：`{data}`；`quarantine/`不在data.yaml的任何split中。',
        '清洗规则与查看记录：policy.json、visual_review.json；输入、脚本、源标注哈希：build.json和脚本快照；隔离的所有原始框：isolated_annotations.json。',
        f'选择指纹（不含绝对输出路径）：`{fingerprint}`。相同源数据、规则和证据应得到相同指纹。', '',
        '```powershell', 'cd F:\\code\\tongue-analysis\\tongue-analysis',
        '. .\\research\\use-e-storage.ps1',
        '# 已有v1拒绝覆盖；复现到新目录',
        '.\\research\\.venv\\Scripts\\python.exe research\\training\\clean_dataset.py --output research\\datasets\\clean_v1_rebuild --logs research\\results\\clean_v1_rebuild',
        '.\\research\\.venv\\Scripts\\python.exe research\\training\\audit_clean.py --data research\\datasets\\clean_v1_rebuild --logs research\\results\\clean_v1_rebuild',
        '.\\research\\.venv\\Scripts\\python.exe research\\training\\summarize_clean.py --data research\\datasets\\clean_v1_rebuild --logs research\\results\\clean_v1_rebuild', '```','',
        '## 从官方预训练权重开始', '',
        '下面命令加载research/weights/yolo11n.pt（官方v8.3.0 assets），不加载先前21类冒烟权重。权重哈希在delivery.json；不是随机初始化。实际配置、依赖、种子及权重会由训练脚本保存。默认100轮、patience=20、imgsz=640、batch=4、workers=0、seed=42；显存不足减半batch并记录，CUDA不可用停止。', '',
        '```powershell', 'cd F:\\code\\tongue-analysis\\tongue-analysis', '. .\\research\\use-e-storage.ps1',
        '.\\research\\.venv\\Scripts\\python.exe research\\training\\train.py --weights research\\weights\\yolo11n.pt --data research\\datasets\\clean_v1\\data.yaml --epochs 100 --batch 4 --name clean-v1-yolo11n-seed42',
        '# 调参仅使用验证集；模型和阈值固定后才另行最终测试',
        '.\\research\\.venv\\Scripts\\python.exe research\\evaluation\\evaluate.py --weights research\\results\\formal\\clean-v1-yolo11n-seed42\\weights\\best.pt --data research\\datasets\\clean_v1\\data.yaml --split val --name clean-v1-val', '```', '',
        '旧21类配置继续保留；本次将配置读取改为核对实际nc、连续ID和审计来源，使7类子集可训练。启动前还会检查有效图片集合及图像/标签哈希，改过副本需重新审计。无需修改小程序、后端或模型接口。']
    (logs/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Final decision tables, reproducibility fingerprint and training commands saved. Training not started.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'datasets'/'clean_v1')
    p.add_argument('--logs',type=Path,default=ROOT/'results'/'clean_v1')
    summarize(p.parse_args())
