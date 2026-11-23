import gc
import os
import time
from threading import Lock
from pathlib import Path
from PIL import Image, ImageOps
from contracts import messages, parse_output

MODEL_ID = 'Qwen/Qwen3-VL-2B-Instruct'
REVISION = '89644892e4d85e24eaac8bacfd4f463576704203'

def load_model(adapter=None):
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required for this 4-bit baseline')
    model_id = os.getenv('QWEN_MODEL', MODEL_ID)
    max_pixels = int(os.getenv('QWEN_MAX_PIXELS', 256*32*32))
    revision = os.getenv('QWEN_REVISION', REVISION)
    offline = os.getenv('QWEN_OFFLINE', 'false').lower() == 'true'
    processor = AutoProcessor.from_pretrained(model_id, revision=revision, local_files_only=offline, min_pixels=min(128*32*32, max_pixels),
                                             max_pixels=max_pixels)
    model = Qwen3VLForConditionalGeneration.from_pretrained(model_id,
        revision=revision,
        local_files_only=offline,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16, device_map={'': 0}, attn_implementation='sdpa')
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    return model, processor

def prepare(processor, image, symptoms, detections, chunks, mode):
    picture = None
    if mode in ('image', 'both'):
        with Image.open(image) as im:
            picture = ImageOps.exif_transpose(im).convert('RGB')
    conversation = messages(picture, symptoms, detections, chunks, mode)
    return processor.apply_chat_template(conversation, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors='pt')

class Engine:
    def __init__(self, adapter=None):
        self.lock = Lock()
        started = time.perf_counter()
        self.model, self.processor = load_model(adapter)
        self.model.eval()
        self.load_seconds = time.perf_counter()-started

    def infer(self, image, symptoms, detections, chunks, mode='both'):
        import torch
        with self.lock, torch.inference_mode():
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            start = time.perf_counter()
            # Only short aliases and verbatim text enter the prompt; provenance stays in the backend.
            aliases = {f'E{i+1}': c['chunk_id'] for i,c in enumerate(chunks)}
            prompt_chunks = [{'chunk_id': f'E{i+1}', 'text': c['text']} for i,c in enumerate(chunks)]
            prepare_started = time.perf_counter()
            batch = prepare(self.processor, image, symptoms, detections, prompt_chunks, mode).to(self.model.device)
            prepare_seconds = time.perf_counter()-prepare_started
            generation_started = time.perf_counter()
            if batch.input_ids.shape[1] > int(os.getenv('QWEN_MAX_INPUT_TOKENS', '3072')):
                raise ValueError('Input too long; reduce evidence or image pixels')
            generated = self.model.generate(**batch, max_new_tokens=int(os.getenv('QWEN_MAX_NEW_TOKENS', '384')),
                                            # Keep the limit longer than a source chunk_id so copying legal IDs remains possible.
                                            do_sample=False, repetition_penalty=1.05, no_repeat_ngram_size=32)
            raw = self.processor.batch_decode(generated[:, batch.input_ids.shape[1]:], skip_special_tokens=True)[0]
            torch.cuda.synchronize()
            metrics = {'seconds': time.perf_counter()-start,
                       'peak_allocated_mib': torch.cuda.max_memory_allocated()/2**20,
                       'peak_reserved_mib': torch.cuda.max_memory_reserved()/2**20,
                       'input_tokens': batch.input_ids.shape[1],
                       'output_tokens': generated.shape[1]-batch.input_ids.shape[1]}
            metrics.update(preprocess_seconds=prepare_seconds, generation_seconds=time.perf_counter()-generation_started)
            try:
                output = parse_output(raw, prompt_chunks)
                output['cited_chunk_ids'] = [aliases[i] for i in output['cited_chunk_ids']]
                if mode != 'image' and symptoms.strip() and not output['symptoms_summary'].strip():
                    raise ValueError('Qwen omitted the symptoms summary')
                return {'status': 'valid', 'output': output, 'raw_output': raw, 'metrics': metrics}
            except ValueError as exc:
                return {'status': 'invalid_output', 'error': str(exc), 'raw_output': raw, 'metrics': metrics}
