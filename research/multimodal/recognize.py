"""Use the attribute adapter with its actual training prompt (no symptoms invented)."""
import argparse
import json
import time
from pathlib import Path
from train import conversation
from runtime import load_model

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--image', required=True)
    p.add_argument('--adapter', required=True)
    p.add_argument('--output', default='research/multimodal/results/recognition.json')
    a = p.parse_args()
    import torch
    model, processor = load_model(a.adapter)
    model.eval()
    prompt = conversation({'image': a.image}, 'recognition', 'image')
    batch = processor.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors='pt').to(model.device)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(**batch, do_sample=False, max_new_tokens=256)
    torch.cuda.synchronize()
    raw = processor.batch_decode(generated[:, batch.input_ids.shape[1]:], skip_special_tokens=True)[0]
    result = {'raw_output': raw, 'seconds': time.perf_counter()-start,
              'peak_allocated_mib': torch.cuda.max_memory_allocated()/2**20}
    try:
        output = json.loads(raw)
        names = {'hongshe', 'zishe', 'liewenshe', 'chihenshe', 'baitaishe', 'huangtaishe', 'heitaishe'}
        positives, unknown = output['annotated_attributes'], output['unknown_attributes']
        if (set(output) != {'annotated_attributes', 'unknown_attributes'} or
            not isinstance(positives, list) or not isinstance(unknown, list) or
            set(positives) & set(unknown) or set(positives) | set(unknown) != names):
            raise ValueError('Invalid attribute output')
        result.update(status='valid', output=output)
    except (ValueError, TypeError, KeyError):
        result['status'] = 'invalid_output'
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
