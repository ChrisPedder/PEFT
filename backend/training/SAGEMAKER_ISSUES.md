# SageMaker Training Issues & Solutions

Reference for issues encountered running QLoRA fine-tuning on the
SageMaker HuggingFace PyTorch container
(`2.1.0-transformers4.36.0-gpu-py310-cu121-ubuntu20.04`).

---

## 1. Tokenizer incompatibility with Mistral v0.3

**Symptom:** Training fails immediately with:

```
TypeError: Object of type PyPreTokenizerTypeWrapper is not JSON serializable
```

**Cause:** The container ships `transformers==4.36.0` / `tokenizers==0.15.0`,
which are too old to parse the pre-tokenizer config in
`mistralai/Mistral-7B-Instruct-v0.3`.

**Fix:** Upgrade via `requirements.txt` installed at the top of `train.py`:

```
transformers==4.43.4
tokenizers>=0.19.1
```

The pip install runs before any ML library imports, guarded by
`os.environ.get("SM_MODEL_DIR")` so it only executes inside SageMaker.

---

## 2. `dispatch_model` calling `.to()` on quantized models

**Symptom:** Training fails during model loading with:

```
ValueError: `.to` is not supported for `4-bit` or `8-bit` bitsandbytes models.
Please use the model as it is, since the model has already been set to the
correct devices and casted to the correct `dtype`.
```

The traceback points to `accelerate/big_modeling.py` → `dispatch_model` →
`model.to(device)`.

**Cause:** Older `accelerate` versions (< 1.0) unconditionally call
`model.to(device)` inside `dispatch_model()`, which fails on BitsAndBytes
4-bit quantized models (they're already on the correct device after loading).

**Fix (two-part):**

1. **Pin `accelerate>=1.0.0`** in `requirements.txt`. Version 1.0+ has the
   native fix — it skips `.to()` on already-quantized models.

2. **Monkey-patch `dispatch_model`** as a safety net, wrapping the original
   to catch the specific `ValueError` and return the model as-is:

   ```python
   try:
       import accelerate
       import accelerate.big_modeling as _abm

       _original_dispatch = _abm.dispatch_model

       def _safe_dispatch(model, device_map, *args, **kwargs):
           try:
               return _original_dispatch(model, device_map, *args, **kwargs)
           except ValueError as e:
               if ".to" in str(e) and ("4-bit" in str(e) or "8-bit" in str(e)):
                   return model
               raise

       _abm.dispatch_model = _safe_dispatch
       if hasattr(accelerate, "dispatch_model"):
           accelerate.dispatch_model = _safe_dispatch
   except ImportError:
       pass
   ```

### Critical: import ordering matters

The monkey-patch **must** run before `from transformers import ...`. When
transformers is imported, it does `from accelerate import dispatch_model`
internally, caching a direct reference to the function object. Patching
the module attribute *after* that point has no effect — transformers still
holds the original reference.

Both `accelerate.big_modeling.dispatch_model` and `accelerate.dispatch_model`
(the re-exported name) must be patched, since transformers may import from
either location depending on the version.

Correct order in `train.py`:

```
stdlib imports
pip install (SageMaker only)
import torch
import accelerate + apply monkey-patch   ← before transformers
from transformers import ...
from trl import ...
```

---

## 3. SFTTrainer deprecation warnings (trl >= 0.11)

**Symptom:** Warnings during training:

```
FutureWarning: Deprecated argument(s) used in '__init__': max_seq_length,
dataset_text_field, packing. Will not be supported from version '1.0.0'.
```

**Cause:** `trl>=0.11` introduced `SFTConfig` (extends `TrainingArguments`)
and expects SFT-specific parameters to be passed there instead of directly
to the `SFTTrainer` constructor.

**Fix:** Use `SFTConfig` instead of `TrainingArguments`:

```python
from trl import SFTConfig, SFTTrainer

sft_config = SFTConfig(
    output_dir=output_dir,
    # ... all TrainingArguments fields ...
    max_seq_length=2048,       # was in SFTTrainer()
    dataset_text_field="text", # was in SFTTrainer()
    packing=True,              # was in SFTTrainer()
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    tokenizer=tokenizer,
    args=sft_config,
)
```

---

## 4. Container package upgrade strategy

The SageMaker HuggingFace container has fixed package versions that may be
too old for newer model architectures. The approach used here:

1. Bundle a `requirements.txt` alongside `train.py` (both uploaded to S3
   as `sourcedir.tar.gz`).
2. At the top of `train.py`, before any ML imports, run
   `pip install -r requirements.txt` via `subprocess.check_call`.
3. Guard with `os.environ.get("SM_MODEL_DIR")` so it only runs inside
   SageMaker, not during local development or testing.

The container used here already had the upgraded packages cached from a
previous run of the same instance type, so subsequent pip installs show
`Requirement already satisfied`. First runs on a fresh container will
take longer as packages are downloaded and installed.

### Container defaults (for reference)

| Package        | Container version | Required version |
|----------------|-------------------|------------------|
| transformers   | 4.36.0            | 4.43.4           |
| tokenizers     | 0.15.0            | >=0.19.1         |
| accelerate     | 0.26.0            | >=1.0.0          |
| peft           | (not installed)   | 0.14.0           |
| trl            | (not installed)   | 0.11.4           |
| bitsandbytes   | (not installed)   | >=0.43.0         |
