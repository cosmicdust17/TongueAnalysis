from pathlib import Path
from .core import QUERY_PREFIX, query_text
from .evaluation import validate_labels
from .io_utils import digest, rows, write_json


def train(kind, corpus, labels, output, model, epochs=1, batch_size=8):
    chunks = {c['chunk_id']: c for c in rows(corpus)}
    labels_data = rows(labels)
    validate_labels(labels_data, chunks)
    if any(v.get('is_demo') for v in labels_data) or any(c.get('is_demo') for c in chunks.values()):
        raise ValueError('Synthetic data cannot be used for real fine-tuning')
    if not any(v['split'] == 'train' for v in labels_data) or not any(v['split'] == 'validation' for v in labels_data):
        raise ValueError('Separate human-verified train and validation queries required')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Training output directory must be new/empty')
    from datasets import Dataset
    from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer, SentenceTransformerTrainingArguments
    from sentence_transformers import losses
    from sentence_transformers.cross_encoder import CrossEncoder, CrossEncoderTrainer, CrossEncoderTrainingArguments
    from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss
    datasets = {}
    for split in ('train', 'validation'):
        data = []
        for row in labels_data:
            if row['split'] != split:
                continue
            query = query_text(row['symptoms'], row.get('tongue_features'))
            if not row['hard_negative_chunk_ids']:
                raise ValueError('Provide reviewed hard negatives for training')
            for positive in row['relevant_chunk_ids']:
                if kind == 'embedding':
                    for negative in row['hard_negative_chunk_ids']:
                        data.append({'anchor': QUERY_PREFIX + query, 'positive': chunks[positive]['text'],
                                     'negative': chunks[negative]['text']})
                else:
                    data.append({'sentence1': query, 'sentence2': chunks[positive]['text'], 'label': 1.0})
            if kind == 'reranker':
                data.extend({'sentence1': query, 'sentence2': chunks[n]['text'], 'label': 0.0} for n in row['hard_negative_chunk_ids'])
        datasets[split] = Dataset.from_list(data)
    common = dict(output_dir=str(output), num_train_epochs=epochs, per_device_train_batch_size=batch_size,
                  per_device_eval_batch_size=batch_size, eval_strategy='epoch', save_strategy='epoch',
                  load_best_model_at_end=True, metric_for_best_model='eval_loss', greater_is_better=False,
                  seed=42, report_to='none', learning_rate=2e-5)
    if kind == 'embedding':
        encoder = SentenceTransformer(model, local_files_only=True)
        encoder.max_seq_length = 512
        trainer = SentenceTransformerTrainer(model=encoder, args=SentenceTransformerTrainingArguments(**common),
            train_dataset=datasets['train'], eval_dataset=datasets['validation'], loss=losses.TripletLoss(encoder))
    else:
        encoder = CrossEncoder(model, local_files_only=True, num_labels=1, max_length=512)
        trainer = CrossEncoderTrainer(model=encoder, args=CrossEncoderTrainingArguments(**common),
            train_dataset=datasets['train'], eval_dataset=datasets['validation'], loss=BinaryCrossEntropyLoss(encoder))
    trainer.train()
    encoder.save_pretrained(str(output / 'final'))
    write_json(output / 'training_manifest.json', {'kind': kind, 'base_model': model, 'labels_hash': digest(labels_data),
        'corpus_hash': digest(list(chunks.values())), 'seed': 42, 'epochs': epochs,
        'next_step': 'Rebuild vectors and ingest new index' if kind == 'embedding' else 'Reuse embedding index; change RETRIEVAL_RERANKER'})
