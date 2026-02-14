---
title: "Loading quantized adaptor models for CPU inference"
date: 2026-02-07
draft: false
tags: ["ai"]
---

I had fine tuned a large language model via an [adaptor](https://huggingface.co/docs/hub/adapters) on google colab 
using a GPU that had significantly more VRAM than my GPU at home. I had intended to load it onto my CPU for inference
to test out a few things but had some serious issues getting it working:

# Issue 1: Don't load in via 4-bit for CPU
You can't **entirely** offload a 4 bit quantized model to CPU, it needs to be GPU, 
if you try to you'll get the error
```python
from unsloth import FastLanguageModel
model_name  = "unsloth/Qwen3-14B-unsloth-bnb-4bit"
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = 1024,
    load_in_4bit = True,
    load_in_8bit = False,
    full_finetuning = False
)
model.load_adapter("/home/stephen/Downloads/qmodel/qwen_new2/checkpoint-440")
```
```zsh
ValueError: Some modules are dispatched on the CPU or the disk. Make sure you have enough GPU RAM to fit the quantized model. 
If you want to dispatch the model on the CPU or the disk while keeping these modules in 32-bit, 
you need to set `llm_int8_enable_fp32_cpu_offload=True` and pass a custom `device_map` to `from_pretrained`. 
Check https://huggingface.co/docs/transformers/main/en/main_classes/quantization#offload-between-cpu-and-gpu for more details. 
```

Trying to google around `llm_int8_enable_fp32_cpu_offload` will lead you down a lot of confusing paths,
most of which won't work.

The actual solution is simple.

CPU based inference doesn't support 4 bit mode, those layers need to be moved to a GPU. If your entire goal is to just
run using CPU inference then the important thing to know is that even if you have **trained** for model in 4 bit quantized mode,
you don't need to **load** your model in 4 bit quantized mode when doing inference. Instead, represent the 4 bit datatypes
with a `bfloat16` or `float32` (from my reading [at one point float16 had some issues when running on CPU, not sure if this is fixed](https://discuss.pytorch.org/t/cpu-train-network-using-float-16/213486))

You will not gain any additional quality in doing this (You're still representing the same 4 bit number) however 
you **will** consume significantly more memory, but chances are that if you're doing CPU based inference,
you're doing it because your model wont fit within your GPU memory, not becuase you think it's optimal.


```python
from unsloth import FastLanguageModel

model_name  = "unsloth/Qwen3-14B-unsloth-bnb-4bit"
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = 1024,
    load_in_4bit = False, # Fix: Dont load in 4 bit mode
    load_in_8bit = False,
    full_finetuning = False,
    torch_dtype="bfloat16" # Fix: Use a dtype that CPUs support.
)
model.load_adapter("checkpoint-440")
```

# Issue 2: Don't use unsloth load models for CPU inference
Unsloth is great, one of the reasons for this is that it loads in 
a lot of [Triton based](https://docs.pytorch.org/tutorials/recipes/torch_compile_user_defined_triton_kernel_tutorial.html)
custom kernels that are significantly faster.

Because these kernels are written to be executed on a GPU to take advantage of massive parallel processes, they may
not work properly on CPUs, leading to errors like this.
```zsh
ValueError: Pointer argument (at 0) cannot be accessed from Triton (cpu tensor?)
```

Instead load in your adapter using [transformers](https://huggingface.co/docs/transformers/index), 
this will work even if you used unsloth to train your model.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from pathlib import Path

# This is the exact same loading process as the unsloth method, but using the transformers package
# so that you don't get patched Triton kernels
model_name = "unsloth/Qwen3-14B-unsloth-bnb-4bit"
tokenizer = AutoTokenizer.from_pretrained(model_name)
base_model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="cpu",
    torch_dtype="float32",
)
model = PeftModel.from_pretrained(base_model, "checkpoint-440")
```


