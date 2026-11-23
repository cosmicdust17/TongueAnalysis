"""Single-GPU QLoRA, supervised assistant tokens only, actual reload verification."""
import argparse
import gc
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from PIL import Image, ImageOps
from contracts import messages, Output
from runtime import load_model

RECOGNITION_PROMPT = '仅返回JSON，字段annotated_attributes和unknown_attributes为类别名称数组。识别舌照中的已标注舌象属性，未标注类别状态未知，不推断为不存在。类别：hongshe,zishe,liewenshe,chihenshe,baitaishe,huangtaishe,heitaishe。'

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]

def validate_rows(rows, task, split):
    if not rows:
        raise ValueError('Empty dataset')
    for r in rows:
        if r['split'] != split or r.get('is_simulated') or not Path(r['image']).is_file():
            raise ValueError('Require real cases from the declared train/val split')
        if task == 'joint':
            if not r.get('symptoms') or r.get('reference_kind') != 'paired_case':
                raise ValueError('Joint training requires same-case image, symptoms and reviewed reference')
            Output.model_validate(r['reference'])
        elif r.get('reference_kind') != 'detection_annotations':
            raise ValueError('Recognition requires detection annotations')
        if task == 'joint' and r['reference']['cited_chunk_ids']:
            raise ValueError('No retrieved evidence supplied in this joint-data format; citation IDs must be empty')

def conversation(row, task, mode):
    with Image.open(row['image']) as im:
        image = ImageOps.exif_transpose(im).convert('RGB')
    if task == 'recognition':
        if mode != 'image':
            raise ValueError('Detection-only data cannot train symptoms or fusion')
        return [{'role': 'system', 'content': [{'type': 'text', 'text': RECOGNITION_PROMPT}]},
                {'role': 'user', 'content': [{'type': 'image', 'image': image}]}]
    return messages(image, row['symptoms'], [], [], mode)

def run(a):
    import torch
    from peft import get_peft_model, prepare_model_for_kbit_training, LoraConfig
    from transformers import set_seed
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'stage': 'data_validation', 'parameters': vars(a),
              'command': subprocess.list2cmdline([sys.executable, *sys.argv]), 'steps_completed': 0}
    from runtime import MODEL_ID, REVISION
    report['runtime'] = {'base_model': os.getenv('QWEN_MODEL', MODEL_ID),
        'revision': os.getenv('QWEN_REVISION', REVISION),
        'max_pixels': int(os.getenv('QWEN_MAX_PIXELS', 262144)), 'seed': 42,
        'batch_size': 1, 'torch': torch.__version__, 'cuda': torch.version.cuda,
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}
    started = time.perf_counter()
    try:
        train, val = read_rows(a.train), read_rows(a.val)
        validate_rows(train, a.task, 'train')
        validate_rows(val, a.task, 'val')
        if {r['case_id'] for r in train} & {r['case_id'] for r in val}:
            raise ValueError('Train/val case_id leakage')
        train_hashes = {r.get('image_sha256') or __import__('hashlib').sha256(Path(r['image']).read_bytes()).hexdigest() for r in train}
        if any((r.get('image_sha256') or __import__('hashlib').sha256(Path(r['image']).read_bytes()).hexdigest()) in train_hashes for r in val):
            raise ValueError('Train/val leakage')
        if a.steps < 1:
            raise ValueError('At least one actual optimizer step required')
        set_seed(42)
        report['stage'] = 'load_4bit'
        model, processor = load_model()
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={'use_reentrant': False})
        model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
            target_modules=r'.*language_model.*\.(q_proj|v_proj)$', task_type='CAUSAL_LM'))
        model.config.use_cache = False
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
        model.train()
        torch.cuda.reset_peak_memory_stats()
        report['stage'] = 'train'
        losses = []
        gradient_norms = []
        train_started = time.perf_counter()
        for step in range(a.steps):
            row = train[step % min(a.samples, len(train))]
            prompt = conversation(row, a.task, a.mode)
            full = prompt + [{'role': 'assistant', 'content': [{'type': 'text',
                'text': json.dumps(row['reference'], ensure_ascii=False)}]}]
            prefix = processor.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors='pt')
            batch = processor.apply_chat_template(full, tokenize=True, add_generation_prompt=False,
                return_dict=True, return_tensors='pt').to(model.device)
            if batch.input_ids.shape[1] > a.max_length:
                raise ValueError('Sequence exceeds max-length; lower pixels or shorten text, never truncate image tokens')
            labels = batch.input_ids.clone()
            labels[:, :prefix.input_ids.shape[1]] = -100
            if not (labels != -100).any():
                raise ValueError('No assistant supervision tokens')
            loss = model(**batch, labels=labels).loss
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite loss')
            loss.backward()
            gradient_norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            if not torch.isfinite(gradient_norm) or gradient_norm.item() == 0:
                raise ValueError('No finite nonzero adapter gradient')
            gradient_norms.append(float(gradient_norm))
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            losses.append(float(loss.detach()))
            report['steps_completed'] += 1
            print(json.dumps({'step': step+1, 'loss': losses[-1]}), flush=True)
            del batch, prefix, labels, loss
        torch.cuda.synchronize()
        report.update(losses=losses, gradient_norms=gradient_norms, train_seconds=time.perf_counter()-train_started,
                      train_peak_allocated_mib=torch.cuda.max_memory_allocated()/2**20,
                      train_peak_reserved_mib=torch.cuda.max_memory_reserved()/2**20)
        report['stage'] = 'save_adapter'
        model.save_pretrained(out / 'adapter')
        processor.save_pretrained(out / 'adapter')
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()
        report['stage'] = 'reload_and_infer'
        model, processor = load_model(str(out / 'adapter'))
        model.eval()
        prompt = conversation(val[0], a.task, a.mode)
        batch = processor.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors='pt').to(model.device)
        torch.cuda.reset_peak_memory_stats()
        inference_started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**batch, max_new_tokens=256, do_sample=False)
        torch.cuda.synchronize()
        raw = processor.batch_decode(generated[:, batch.input_ids.shape[1]:], skip_special_tokens=True)[0]
        report.update(reload_inference_seconds=time.perf_counter()-inference_started,
            reload_peak_allocated_mib=torch.cuda.max_memory_allocated()/2**20, reload_output=raw)
        # Smoke success proves training/save/reload/inference, not accuracy after a few steps.
        if not raw.strip():
            raise ValueError('Reload inference produced no output')
        report.update(status='passed', stage='complete')
    except Exception:
        report['traceback'] = traceback.format_exc()
        raise
    finally:
        report['total_seconds'] = time.perf_counter()-started
        (out / 'run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--task', choices=['recognition', 'joint'], default='recognition')
    p.add_argument('--mode', choices=['image', 'symptoms', 'both'], default='image')
    p.add_argument('--train', default='research/multimodal/data/recognition/train.jsonl')
    p.add_argument('--val', default='research/multimodal/data/recognition/val.jsonl')
    p.add_argument('--output', default='research/multimodal/results/qlora-smoke')
    p.add_argument('--steps', type=int, default=2)
    p.add_argument('--samples', type=int, default=4)
    p.add_argument('--max-length', type=int, default=1024)
    p.add_argument('--lr', type=float, default=2e-4)
    run(p.parse_args())
