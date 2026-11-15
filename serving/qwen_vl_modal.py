"""An open vision model as an OpenAI-compatible endpoint on Modal (vLLM), for OpenCode under Harbor.

    MODEL_VARIANT=qwen-2b    .venv/bin/modal deploy serving/qwen_vl_modal.py   # Qwen3-VL-2B-Thinking, one L40S (default)
    MODEL_VARIANT=qwen-32b   .venv/bin/modal deploy serving/qwen_vl_modal.py   # Qwen3-VL-32B-Thinking, one H200
    MODEL_VARIANT=gemma4-31b .venv/bin/modal deploy serving/qwen_vl_modal.py   # Gemma 4 31B (google/gemma-4-31B-it), one H200
    MODEL_VARIANT=qwen38-27b .venv/bin/modal deploy serving/qwen_vl_modal.py   # Qwen3.8-27B, one H200
    MODEL_VARIANT=qwen35-9b  .venv/bin/modal deploy serving/qwen_vl_modal.py   # Qwen3.5-9B, one L40S
    MODEL_VARIANT=qwen35-9b-ft FT_RUN=<run> .venv/bin/modal deploy serving/qwen_vl_modal.py   # the fine-tuned Qwen3.5-9B of that training run
    .venv/bin/modal app stop <app name>                    # when done (each also scales to zero after 15 idle minutes)

Deploy prints the URL; the endpoint is <URL>/v1. App and model names per variant are in VARIANTS below.
The key: a Modal secret `sweep-qwen-key` with QWEN_API_KEY, the same value as MODAL_QWEN_API_KEY in .env:
    .venv/bin/modal secret create sweep-qwen-key QWEN_API_KEY=<value of MODAL_QWEN_API_KEY>

One GPU per variant; nothing starts more than one container. vLLM parses the model's tool calls and returns
its thinking separately from its answer; up to 64 pictures may be in one request (an agent's conversation
keeps the earlier camera pictures).
"""
import os
import subprocess

import modal

VARIANTS = {
    # variant: Modal app, Hugging Face id, model name served, GPU, longest prompt + answer (tokens), vLLM tool-call and reasoning parsers
    "qwen-2b": dict(app="sweep-qwen3-vl-2b", hf="Qwen/Qwen3-VL-2B-Thinking", served="qwen3-vl-2b-thinking", gpu="L40S", max_len=65536, tools="hermes", reasoning="qwen3"),
    # 67 GB and 63 GB of weights in bf16: more than an 80 GB card holds together with the cache for a long prompt
    "qwen-32b": dict(app="sweep-qwen3-vl-32b", hf="Qwen/Qwen3-VL-32B-Thinking", served="qwen3-vl-32b-thinking", gpu="H200", max_len=110000, tools="hermes", reasoning="qwen3"),
    "gemma4-31b": dict(app="sweep-gemma4-31b", hf="google/gemma-4-31B-it", served="gemma-4-31b-it", gpu="H200", max_len=110000, tools="gemma4", reasoning="gemma4"),
    # flags from vLLM's recipe for this model (recipes.vllm.ai/Qwen/Qwen3.8-27B); it thinks by default
    "qwen38-27b": dict(app="sweep-qwen38-27b", hf="Qwen/Qwen3.8-27B", served="qwen3.8-27b", gpu="H200", max_len=110000, tools="qwen3_coder", reasoning="qwen3",
                       extra=["--mm-encoder-tp-mode", "data"]),
    "qwen35-9b": dict(app="sweep-qwen35-9b", hf="Qwen/Qwen3.5-9B", served="qwen3.5-9b", gpu="L40S", max_len=110000, tools="qwen3_coder", reasoning="qwen3",
                      extra=["--mm-encoder-tp-mode", "data"]),      # 19 GB of weights; same family and flags as Qwen3.8
    # Qwen3.5-9B fine-tuned on the camera task (training/camera_sft_modal.py): the merged model on the volume, thinking off as in training
    "qwen35-9b-ft": dict(app="sweep-qwen35-9b-ft", hf="/root/.cache/huggingface/ft/" + os.environ.get("FT_RUN", "smoke"), served="qwen3.5-9b-sweep",
                         gpu="L40S", max_len=110000, tools="qwen3_coder", reasoning="qwen3",
                         extra=["--mm-encoder-tp-mode", "data", "--default-chat-template-kwargs", '{"enable_thinking": false}']),
    # the same fine-tuned model with thinking left on (a mode it was never trained in)
    "qwen35-9b-ft-think": dict(app="sweep-qwen35-9b-ft-think", hf="/root/.cache/huggingface/ft/" + os.environ.get("FT_RUN", "smoke"), served="qwen3.5-9b-sweep",
                               gpu="L40S", max_len=110000, tools="qwen3_coder", reasoning="qwen3", extra=["--mm-encoder-tp-mode", "data"]),
}
VARIANT = os.environ.get("MODEL_VARIANT", "qwen-2b")
V = VARIANTS[VARIANT]

# The CUDA "devel" image: vLLM's sampler (flashinfer) compiles a kernel at start and needs nvcc for it.
image = (modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12")
         .entrypoint([]).pip_install("vllm==0.33.0").env({"MODEL_VARIANT": VARIANT, "FT_RUN": os.environ.get("FT_RUN", "smoke")}))
app = modal.App(V["app"])
hf_cache = modal.Volume.from_name("sweep-hf-cache", create_if_missing=True)


@app.function(image=image, gpu=V["gpu"], max_containers=1, scaledown_window=15 * 60, timeout=6 * 60 * 60,
              volumes={"/root/.cache/huggingface": hf_cache}, secrets=[modal.Secret.from_name("sweep-qwen-key")])
@modal.concurrent(max_inputs=16)
@modal.web_server(port=8000, startup_timeout=45 * 60)
def serve():
    subprocess.Popen([
        "vllm", "serve", V["hf"], "--served-model-name", V["served"], "--host", "0.0.0.0", "--port", "8000",
        "--api-key", os.environ["QWEN_API_KEY"], "--max-model-len", str(V["max_len"]),
        "--enable-auto-tool-choice", "--tool-call-parser", V["tools"], "--reasoning-parser", V["reasoning"],
        "--limit-mm-per-prompt", '{"image": 64}',
    ] + V.get("extra", []))
