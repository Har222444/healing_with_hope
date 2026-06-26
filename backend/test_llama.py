import sys
import torch
import traceback

sys.stdout.reconfigure(encoding='utf-8')

print("Step 1: importing transformers", flush=True)
from transformers import AutoTokenizer, AutoModelForCausalLM

path = "./trained_models/llama_hope"

print("Step 2: loading tokenizer", flush=True)
tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
print("Step 3: tokenizer ok", flush=True)

print("Step 4: loading model", flush=True)
try:
    model = AutoModelForCausalLM.from_pretrained(
        path,
        dtype=torch.float32,
        device_map="cpu",
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    print("Step 5: model loaded ok", flush=True)
except Exception as e:
    print("FAILED at model load:", flush=True)
    traceback.print_exc()
    sys.exit(1)

print("Step 6: generating", flush=True)
try:
    inputs = tok("i feel sad today", return_tensors="pt")
    out = model.generate(**inputs, max_new_tokens=50, pad_token_id=tok.eos_token_id)
    print("Step 7: output:", tok.decode(out[0], skip_special_tokens=True), flush=True)
except Exception as e:
    print("FAILED at generate:", flush=True)
    traceback.print_exc()