from typing import Optional
import threading
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Local model settings
_MODEL_ID = "google/flan-t5-base"
_tokenizer: Optional[AutoTokenizer] = None
_model: Optional[AutoModelForSeq2SeqLM] = None
_lock = threading.Lock()
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _load_model():
    global _tokenizer, _model
    with _lock:
        if _model is None or _tokenizer is None:
            _tokenizer = AutoTokenizer.from_pretrained(_MODEL_ID)
            _model = AutoModelForSeq2SeqLM.from_pretrained(_MODEL_ID)
            _model.to(_device)


def generate_text(prompt: str, max_new_tokens: int = 200, temperature: float = 0.3) -> str:
    """
    Generate text locally using `google/flan-t5-base`.

    - Lazy loads model/tokenizer once.
    - Uses truncation to avoid unbounded inputs.
    - `max_new_tokens=200`, `temperature=0.3` by default.
    """
    if _model is None or _tokenizer is None:
        _load_model()

    # Tokenize with truncation (ensure not to overflow model max length)
    inputs = _tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1024,
    ).to(_device)

    with torch.no_grad():
        generated_ids = _model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True if temperature > 0 else False,
            temperature=temperature,
        )

    output = _tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    return output