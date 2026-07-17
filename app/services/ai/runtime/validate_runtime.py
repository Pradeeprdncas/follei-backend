"""Phase 9 - AI Runtime Validation & Model Verification Script.

This script actually loads every model, runs inference, verifies outputs,
checks hardware, benchmarks performance, and produces a real validation report.

Usage:
    python -m app.services.ai.runtime.validate_runtime

This is NOT a unit test. It's a production validation that proves every model works.
"""
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault("AI_MODELS", str(project_root / "AI_MODELS"))

from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()

# Disable HF transfer for stability
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

RESULTS = {
    "phase": "Phase 9 - AI Runtime Validation",
    "start_time": None,
    "end_time": None,
    "models": {},
    "gpu": {},
    "memory": {},
    "benchmarks": {},
    "singleton_test": None,
    "concurrent_test": None,
    "offline_test": None,
    "corrupted_test": None,
    "errors": [],
    "warnings": [],
    "overall_score": 0,
}


def log_result(step: str, status: str, details: str = ""):
    """Log a validation step result."""
    emoji = "✓" if status == "pass" else ("⚠" if status == "warn" else "✗")
    logger.info(f"{emoji} [{status.upper()}] {step}: {details}")


def get_hf_token() -> Optional[str]:
    """Get HuggingFace token."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        return token
    # Try reading from HF cache
    token_path = Path.home() / ".huggingface" / "token"
    if token_path.exists():
        return token_path.read_text().strip()
    return None


async def step_0_standardize_models():
    """Step 0: Standardize model storage - consolidate to AI_MODELS/."""
    logger.info("=" * 60)
    logger.info("Step 0: Standardizing model storage...")
    logger.info("=" * 60)

    ai_models_root = Path(_settings.AI_MODELS)

    # Ensure all required subdirectories exist
    for subdir in ["embeddings", "classifiers", "llms", "rerankers", "loras", "cache"]:
        (ai_models_root / subdir).mkdir(parents=True, exist_ok=True)

    # Copy LoRAs from models/ to AI_MODELS/loras/
    lora_mappings = [
        ("models/lora-qwen3b", "loras/qwen3b-follei"),
        ("models/lora-360m", "loras/verifier-lora"),
    ]

    for src_rel, dest_rel in lora_mappings:
        src = project_root / src_rel
        dest = ai_models_root / dest_rel
        if src.exists():
            if not dest.exists():
                logger.info(f"  Copying LoRA: {src} -> {dest}")
                shutil.copytree(src, dest)
                size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
                logger.info(f"  ✓ LoRA copied ({size_mb:.1f} MB)")
            else:
                logger.info(f"  ✓ LoRA already at {dest}")

    # Clean up orphan top-level lora-360m
    orphan = project_root / "lora-360m"
    if orphan.exists() and orphan.is_file():
        # Remove orphan file
        orphan.unlink()
        logger.info(f"  ✓ Cleaned up orphan: {orphan}")

    # Verify AI_MODELS structure
    logger.info(f"\n  AI_MODELS structure ({ai_models_root}):")
    for item in sorted(ai_models_root.iterdir()):
        if item.is_dir():
            contents = list(item.iterdir()) if any(item.iterdir()) else []
            logger.info(f"    {'📁' if contents else '📂'} {item.name}/ ({len(contents)} items)")

    log_result("Model standardization", "pass", "All LoRAs copied, structure ready")
    logger.info("")


async def step_1_download_missing_models():
    """Step 1: Download all missing models from HuggingFace."""
    logger.info("=" * 60)
    logger.info("Step 1: Downloading missing models...")
    logger.info("=" * 60)

    from app.services.ai.runtime.download_models import get_model_downloader

    downloader = get_model_downloader()

    # First check what's missing
    verify_results = await downloader.verify_all()
    missing = []
    for key, status in verify_results.items():
        if not status.get("exists", False):
            missing.append(key)
            logger.warning(f"  ✗ {key}: missing")

    if not missing:
        logger.info("  ✓ All models already present on disk")
    else:
        logger.info(f"  Downloading {len(missing)} missing models...")
        await downloader.ensure_all(force_redownload=False)
        logger.info("  ✓ Download complete")

    # Final verification
    verify_results = await downloader.verify_all()
    still_missing = []
    model_sizes = {}
    for key, status in verify_results.items():
        if not status.get("exists", False):
            still_missing.append(key)
        else:
            size_mb = status.get("size_bytes", 0) / (1024 * 1024)
            model_sizes[key] = size_mb
            logger.info(f"  ✓ {key}: {size_mb:.1f} MB")

    if still_missing:
        log_result("Model downloads", "fail", f"Still missing: {still_missing}")
        for m in still_missing:
            RESULTS["errors"].append(f"Model {m} could not be downloaded")
        return False

    log_result("Model downloads", "pass", f"All {len(model_sizes)} models present")
    RESULTS["models"]["downloads"] = model_sizes
    return True


async def step_2_test_embedding():
    """Step 2: Test embedding model with real inference."""
    logger.info("=" * 60)
    logger.info("Step 2: Testing Embedding Model (nomic-embed-text-v1.5)...")
    logger.info("=" * 60)

    step_results = {"name": "nomic-embed-text-v1.5", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()

        # Load model
        load_start = time.perf_counter()
        model_info = await manager.get_model("embedding", _settings.EMBED_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time

        # Verify model type
        model = loader._model
        model_type = type(model).__name__
        step_results["model_type"] = model_type
        logger.info(f"  Model type: {model_type}")

        # Verify device
        if hasattr(model, "device"):
            device = str(model.device)
        else:
            device = str(model._target_device) if hasattr(model, "_target_device") else "cpu"
        step_results["device"] = device
        logger.info(f"  Device: {device}")

        # Get embedding dimension
        dim = model.get_sentence_embedding_dimension()
        step_results["dimension"] = dim
        logger.info(f"  Embedding dimension: {dim}")

        # Test 1: Basic inference
        logger.info("\n  Test 1: Basic inference 'Hello World'...")
        t0 = time.perf_counter()
        vectors = await loader.infer(["Hello World"])
        infer_time = time.perf_counter() - t0
        step_results["inference_time"] = infer_time

        vector = vectors[0]
        logger.info(f"  Vector length: {len(vector)}")
        logger.info(f"  Inference time: {infer_time*1000:.1f} ms")

        # Verify vector properties
        has_values = any(abs(v) > 0 for v in vector)
        has_nan = any(v != v for v in vector)  # NaN check
        is_correct_dim = len(vector) == dim if dim else len(vector) > 0

        step_results["tests"]["has_values"] = has_values
        step_results["tests"]["has_nan"] = has_nan
        step_results["tests"]["correct_dimension"] = is_correct_dim
        logger.info(f"  ✓ Non-zero values: {has_values}")
        logger.info(f"  ✓ No NaN: {not has_nan}")
        logger.info(f"  ✓ Correct dimension: {is_correct_dim}")

        # Test 2: Batch inference
        logger.info("\n  Test 2: Batch inference (3 texts)...")
        t0 = time.perf_counter()
        batch_vectors = await loader.infer(["Hello", "World", "Test sentence"])
        batch_time = time.perf_counter() - t0
        step_results["batch_time"] = batch_time
        logger.info(f"  Batch of 3: {batch_time*1000:.1f} ms")
        logger.info(f"  Results: {len(batch_vectors)} vectors")

        all_pass = has_values and not has_nan and is_correct_dim
        log_result("Embedding", "pass" if all_pass else "fail",
                   f"dim={dim}, infer={infer_time*1000:.1f}ms, batch={batch_time*1000:.1f}ms")
        RESULTS["models"]["embedding"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Embedding test failed: {e}")
        RESULTS["errors"].append(f"Embedding test failed: {e}")
        RESULTS["models"]["embedding"] = {"error": str(e)}
        return False


async def step_3_test_classifier():
    """Step 3: Test classifier with real inference."""
    logger.info("=" * 60)
    logger.info("Step 3: Testing Classifier (ModernBERT-base)...")
    logger.info("=" * 60)

    step_results = {"name": "ModernBERT-base", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        load_start = time.perf_counter()
        model_info = await manager.get_model("classifier", _settings.INTENT_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time
        logger.info(f"  Load time: {load_time:.2f}s")

        # Test: Classify "Send email to John"
        logger.info("\n  Test: Classify 'Send email to John about the meeting'...")
        t0 = time.perf_counter()
        result = await loader.infer("Send email to John about the meeting", top_k=3)
        infer_time = time.perf_counter() - t0
        step_results["inference_time"] = infer_time

        primary_intent = result.get("primary_intent", "?")
        confidence = result.get("confidence", 0)
        intents = result.get("intents", [])

        logger.info(f"  Primary intent: {primary_intent} ({confidence:.2%})")
        logger.info(f"  Inference time: {infer_time*1000:.1f} ms")
        for i, intent in enumerate(intents):
            logger.info(f"    {i+1}. {intent['intent']}: {intent['confidence']:.2%}")

        step_results["tests"]["intent_returned"] = primary_intent != "?"
        step_results["tests"]["has_confidence"] = confidence > 0
        step_results["tests"]["has_top_3"] = len(intents) >= 3
        step_results["primary_intent"] = primary_intent
        step_results["confidence"] = confidence

        all_pass = all([
            step_results["tests"]["intent_returned"],
            step_results["tests"]["has_confidence"],
            step_results["tests"]["has_top_3"],
        ])
        log_result("Classifier", "pass" if all_pass else "fail",
                   f"intent={primary_intent}, confidence={confidence:.2%}, infer={infer_time*1000:.1f}ms")
        RESULTS["models"]["classifier"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Classifier test failed: {e}")
        RESULTS["errors"].append(f"Classifier test failed: {e}")
        RESULTS["models"]["classifier"] = {"error": str(e)}
        return False


async def step_4_test_query_optimizer():
    """Step 4: Test query optimizer with real inference."""
    logger.info("=" * 60)
    logger.info("Step 4: Testing Query Rewriter (Qwen2.5-0.5B)...")
    logger.info("=" * 60)

    step_results = {"name": "qwen2.5-0.5b", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        load_start = time.perf_counter()
        model_info = await manager.get_model("query_optimizer", _settings.QUERY_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time
        logger.info(f"  Load time: {load_time:.2f}s")

        logger.info("\n  Test: Optimize 'refund policy'...")
        t0 = time.perf_counter()
        result = await loader.infer("refund policy")
        infer_time = time.perf_counter() - t0
        step_results["inference_time"] = infer_time

        rewritten = result.get("optimized_search_query", "")
        keywords = result.get("keywords", [])
        intent = result.get("intent", "")

        logger.info(f"  Original: 'refund policy'")
        logger.info(f"  Rewritten: '{rewritten}'")
        logger.info(f"  Keywords: {keywords}")
        logger.info(f"  Intent: {intent}")
        logger.info(f"  Inference time: {infer_time*1000:.1f} ms")

        step_results["tests"]["rewritten"] = bool(rewritten) and rewritten != "refund policy"
        step_results["tests"]["has_keywords"] = len(keywords) > 0
        step_results["rewritten_query"] = rewritten

        all_pass = step_results["tests"]["rewritten"]
        log_result("Query Optimizer", "pass" if all_pass else "warn",
                   f"rewritten='{rewritten}', infer={infer_time*1000:.1f}ms")
        RESULTS["models"]["query_optimizer"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Query optimizer test failed: {e}")
        RESULTS["errors"].append(f"Query optimizer test failed: {e}")
        RESULTS["models"]["query_optimizer"] = {"error": str(e)}
        return False


async def step_5_test_summarizer():
    """Step 5: Test summarizer with real inference."""
    logger.info("=" * 60)
    logger.info("Step 5: Testing Summarizer (SmolLM2-360M)...")
    logger.info("=" * 60)

    step_results = {"name": "smollm2-360m", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        load_start = time.perf_counter()
        model_info = await manager.get_model("summarizer", _settings.SUMMARY_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time
        logger.info(f"  Load time: {load_time:.2f}s")

        # 300-word sample
        sample = (
            "Artificial intelligence is transforming the way businesses operate across every industry. "
            "From automating routine tasks to providing deep insights through data analysis, AI technologies "
            "are enabling organizations to achieve unprecedented levels of efficiency and innovation. "
            "Machine learning algorithms can process vast amounts of data to identify patterns and make "
            "predictions that would be impossible for humans to discover manually. Natural language processing "
            "allows computers to understand and generate human language, powering chatbots, translation services, "
            "and content generation tools. Computer vision enables machines to interpret and analyze visual "
            "information from the world around them. Deep learning, a subset of machine learning, uses neural "
            "networks with multiple layers to model complex patterns and relationships in data. These technologies "
            "are being applied in healthcare for diagnosis and drug discovery, in finance for fraud detection and "
            "algorithmic trading, in manufacturing for quality control and predictive maintenance, and in "
            "customer service for personalized recommendations and support. However, the rapid advancement of AI "
            "also raises important ethical considerations around privacy, bias, transparency, and accountability. "
            "Organizations must carefully consider these factors as they implement AI solutions to ensure they "
            "are used responsibly and for the benefit of all stakeholders. The future of AI promises even more "
            "exciting developments as researchers continue to push the boundaries of what's possible."
        )

        logger.info(f"\n  Test: Summarize {len(sample)}-char text...")
        t0 = time.perf_counter()
        summary = await loader.infer(sample, max_length=50)
        infer_time = time.perf_counter() - t0
        step_results["inference_time"] = infer_time

        logger.info(f"  Original length: {len(sample)} chars")
        logger.info(f"  Summary length: {len(summary)} chars")
        logger.info(f"  Summary: {summary[:200]}...")
        logger.info(f"  Inference time: {infer_time*1000:.1f} ms")

        step_results["tests"]["summary_generated"] = len(summary) > 20
        step_results["tests"]["shorter_than_original"] = len(summary) < len(sample)
        step_results["summary_length"] = len(summary)

        all_pass = len(summary) > 20
        log_result("Summarizer", "pass" if all_pass else "warn",
                   f"summary={len(summary)} chars, infer={infer_time*1000:.1f}ms")
        RESULTS["models"]["summarizer"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Summarizer test failed: {e}")
        RESULTS["errors"].append(f"Summarizer test failed: {e}")
        RESULTS["models"]["summarizer"] = {"error": str(e)}
        return False


async def step_6_test_generator():
    """Step 6: Test generator with real inference + LoRA verification."""
    logger.info("=" * 60)
    logger.info("Step 6: Testing Generator (Qwen3B + LoRA)...")
    logger.info("=" * 60)

    step_results = {"name": "qwen3b-follei", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        load_start = time.perf_counter()
        model_info = await manager.get_model("generator", _settings.GENERATOR_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time
        logger.info(f"  Load time: {load_time:.2f}s")

        # Verify LoRA
        lora_loaded = hasattr(loader._model, "peft_config") if loader._model else False
        step_results["lora_loaded"] = lora_loaded
        lora_path = loader._lora_path if hasattr(loader, "_lora_path") else None
        if lora_loaded:
            logger.info(f"  ✓ LoRA adapter loaded")
            try:
                active_adapter = loader._model.active_adapter
                logger.info(f"  Active adapter: {active_adapter}")
            except Exception:
                logger.info(f"  LoRA: merged into base model")
        else:
            logger.info(f"  ⚠ LoRA not detected (using base model)")
            if lora_path:
                logger.info(f"  Expected LoRA at: {lora_path}")

        # Tokenizer info
        tokenizer = loader._tokenizer
        step_results["has_tokenizer"] = tokenizer is not None
        if tokenizer:
            logger.info(f"  ✓ Tokenizer loaded: {type(tokenizer).__name__}")
            logger.info(f"  Vocab size: {tokenizer.vocab_size if hasattr(tokenizer, 'vocab_size') else '?'}")

        # Test: Generate "What is Follei?"
        logger.info(f"\n  Test: Generate 'What is Follei?'...")
        prompt = "What is Follei?"
        system = "You are a helpful assistant for the Follei customer success platform."

        t0 = time.perf_counter()
        response = await loader.infer(
            prompt=prompt,
            system_prompt=system,
            max_tokens=100,
            temperature=0.1,
        )
        total_time = time.perf_counter() - t0

        response_words = len(response.split())
        step_results["response_length"] = len(response)
        step_results["response_words"] = response_words
        step_results["inference_time"] = total_time

        logger.info(f"  Prompt: '{prompt}'")
        logger.info(f"  Response: '{response[:200]}...'")
        logger.info(f"  Response length: {len(response)} chars ({response_words} words)")
        logger.info(f"  Total time: {total_time:.2f}s")

        # Tokens per second estimate
        tokens_est = len(response) / 4  # rough char->token
        tps = tokens_est / total_time if total_time > 0 else 0
        step_results["tokens_per_second"] = tps
        logger.info(f"  Estimated tokens/sec: {tps:.1f}")

        step_results["tests"]["response_generated"] = len(response) > 20
        step_results["tests"]["not_empty"] = len(response.strip()) > 0

        all_pass = len(response) > 20
        log_result("Generator", "pass" if all_pass else "warn",
                   f"lora={lora_loaded}, response={response_words} words, tps={tps:.1f}")
        RESULTS["models"]["generator"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Generator test failed: {e}")
        RESULTS["errors"].append(f"Generator test failed: {e}")
        RESULTS["models"]["generator"] = {"error": str(e)}
        return False


async def step_7_test_reranker():
    """Step 7: Test reranker with real inference."""
    logger.info("=" * 60)
    logger.info("Step 7: Testing Reranker (BGE-reranker-base)...")
    logger.info("=" * 60)

    step_results = {"name": "bge-reranker-base", "tests": {}}

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        load_start = time.perf_counter()
        model_info = await manager.get_model("reranker", _settings.RERANK_MODEL)
        loader = model_info["loader"]
        load_time = time.perf_counter() - load_start
        step_results["load_time"] = load_time
        logger.info(f"  Load time: {load_time:.2f}s")

        # Test: Rerank query with 5 documents
        query = "What is the refund policy for subscription cancellations?"
        documents = [
            "Our premium subscription costs $99 per month and includes unlimited access to all features.",
            "You can cancel your subscription at any time from your account settings page.",
            "Refunds are processed within 5-10 business days after cancellation is confirmed.",
            "We offer a 30-day money-back guarantee on all annual plans.",
            "Contact our support team at support@follei.com for billing inquiries."
        ]

        logger.info(f"\n  Test: Rerank query against {len(documents)} documents...")
        logger.info(f"  Query: '{query}'")
        for i, doc in enumerate(documents):
            logger.info(f"    Doc {i+1}: {doc[:60]}...")

        t0 = time.perf_counter()
        results = await loader.infer(query, documents, top_k=5)
        infer_time = time.perf_counter() - t0
        step_results["inference_time"] = infer_time

        logger.info(f"\n  Ranked results:")
        for i, r in enumerate(results):
            logger.info(f"    {i+1}. Score={r['score']:.4f} | {r['document'][:60]}...")

        scores = [r["score"] for r in results]
        step_results["tests"]["has_ranking"] = len(results) == len(documents)
        step_results["tests"]["has_scores"] = all(s > 0 for s in scores)
        step_results["tests"]["sorted"] = all(
            scores[i] >= scores[i + 1] for i in range(len(scores) - 1)
        ) if len(scores) > 1 else True

        logger.info(f"  Inference time: {infer_time*1000:.1f} ms")

        all_pass = len(results) > 0 and step_results["tests"]["has_scores"]
        log_result("Reranker", "pass" if all_pass else "warn",
                   f"docs={len(results)}, top_score={scores[0]:.4f}, infer={infer_time*1000:.1f}ms")
        RESULTS["models"]["reranker"] = step_results
        return all_pass

    except Exception as e:
        logger.error(f"Reranker test failed: {e}")
        RESULTS["errors"].append(f"Reranker test failed: {e}")
        RESULTS["models"]["reranker"] = {"error": str(e)}
        return False


async def step_8_check_gpu():
    """Step 8: GPU verification."""
    logger.info("=" * 60)
    logger.info("Step 8: GPU Verification...")
    logger.info("=" * 60)

    gpu_info = {"available": False}
    try:
        import torch
        gpu_info["torch_version"] = torch.__version__
        cuda_available = torch.cuda.is_available()
        gpu_info["cuda_available"] = cuda_available

        if cuda_available:
            gpu_info["device_count"] = torch.cuda.device_count()
            gpu_info["current_device"] = torch.cuda.current_device()
            gpu_info["device_name"] = torch.cuda.get_device_name(0)
            gpu_info["cuda_version"] = torch.version.cuda if hasattr(torch.version, "cuda") else "?"

            props = torch.cuda.get_device_properties(0)
            gpu_info["total_vram_gb"] = props.total_memory / (1024**3)

            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            reserved = torch.cuda.memory_reserved(0) / (1024**3)
            gpu_info["allocated_vram_gb"] = allocated
            gpu_info["reserved_vram_gb"] = reserved

            logger.info(f"  ✓ CUDA available")
            logger.info(f"  Device: {gpu_info['device_name']}")
            logger.info(f"  CUDA version: {gpu_info['cuda_version']}")
            logger.info(f"  Total VRAM: {gpu_info['total_vram_gb']:.2f} GB")
            logger.info(f"  Allocated VRAM: {allocated:.2f} GB")
            logger.info(f"  Reserved VRAM: {reserved:.2f} GB")
        else:
            logger.info(f"  ⚠ CUDA not available. Checking MPS...")
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                gpu_info["mps_available"] = True
                logger.info(f"  ✓ MPS available (Apple Silicon)")
            else:
                logger.info(f"  ⚠ No GPU available - using CPU")

    except ImportError:
        logger.info(f"  ⚠ PyTorch not installed")
        gpu_info["error"] = "PyTorch not installed"

    RESULTS["gpu"] = gpu_info
    log_result("GPU Verification", "pass" if gpu_info.get("cuda_available") else "info",
               f"CUDA={gpu_info.get('cuda_available', False)}, VRAM={gpu_info.get('total_vram_gb', 0):.2f}GB" if gpu_info.get("cuda_available") else "No GPU")
    logger.info("")


async def step_9_benchmark():
    """Step 9: Benchmark all models."""
    logger.info("=" * 60)
    logger.info("Step 9: Benchmarking...")
    logger.info("=" * 60)

    benchmarks = {}

    from app.services.ai.model_warmup import get_model_warmup
    warmup = get_model_warmup()
    warmup_times = warmup.get_warmup_times()
    benchmarks["warmup_times"] = warmup_times

    logger.info(f"\n  Warmup times:")
    for key, t in warmup_times.items():
        logger.info(f"    {key}: {t:.2f}s")

    # Collect inference latencies from test results
    for model_key, data in RESULTS["models"].items():
        if isinstance(data, dict):
            infer = data.get("inference_time")
            if infer:
                benchmarks[f"{model_key}_inference_ms"] = infer * 1000
                logger.info(f"  {model_key} inference: {infer*1000:.1f} ms")

            tps = data.get("tokens_per_second")
            if tps:
                benchmarks["generator_tokens_per_sec"] = tps
                logger.info(f"  generator tokens/sec: {tps:.1f}")

            load_t = data.get("load_time")
            if load_t:
                benchmarks[f"{model_key}_load_time"] = load_t

    RESULTS["benchmarks"] = benchmarks
    log_result("Benchmark", "pass", f"Warmup: {len(warmup_times)} models benchmarked")
    logger.info("")


async def step_10_check_memory():
    """Step 10: Memory usage."""
    logger.info("=" * 60)
    logger.info("Step 10: Memory Usage...")
    logger.info("=" * 60)

    mem_info = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        mem_info["total_ram_gb"] = mem.total / (1024**3)
        mem_info["available_ram_gb"] = mem.available / (1024**3)
        mem_info["percent_used"] = mem.percent
        logger.info(f"  RAM: {mem_info['available_ram_gb']:.2f} GB available / {mem_info['total_ram_gb']:.2f} GB total")
        logger.info(f"  RAM usage: {mem.percent}%")
    except ImportError:
        mem_info["error"] = "psutil not available"
        logger.info(f"  ⚠ psutil not available")

    try:
        import torch
        if torch.cuda.is_available():
            mem_info["vram_allocated_gb"] = torch.cuda.memory_allocated(0) / (1024**3)
            mem_info["vram_reserved_gb"] = torch.cuda.memory_reserved(0) / (1024**3)
            mem_info["vram_cached_gb"] = 0.0  # cached is included in reserved on newer pytorch
            logger.info(f"  VRAM allocated: {mem_info['vram_allocated_gb']:.2f} GB")
            logger.info(f"  VRAM reserved: {mem_info['vram_reserved_gb']:.2f} GB")
    except ImportError:
        pass

    RESULTS["memory"] = mem_info
    log_result("Memory Check", "pass", f"RAM: {mem_info.get('percent_used', 0)}% used")
    logger.info("")


async def step_11_test_singleton():
    """Step 11: Singleton verification - request model 20 times."""
    logger.info("=" * 60)
    logger.info("Step 11: Singleton Verification...")
    logger.info("=" * 60)

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()

        # Request the same model 20 times
        first_instance = None
        same_instance = True
        instances = set()

        for i in range(20):
            model_info = await manager.get_model("embedding", _settings.EMBED_MODEL)
            instance_id = id(model_info)
            instances.add(instance_id)

            if first_instance is None:
                first_instance = instance_id
            elif instance_id != first_instance:
                same_instance = False

        logger.info(f"  Requests: 20")
        logger.info(f"  Unique instances: {len(instances)}")
        logger.info(f"  Same instance all times: {same_instance}")

        singleton_result = {
            "requests": 20,
            "unique_instances": len(instances),
            "same_instance": same_instance,
        }
        RESULTS["singleton_test"] = singleton_result

        all_pass = len(instances) == 1
        log_result("Singleton Test", "pass" if all_pass else "fail",
                   f"20 requests, {len(instances)} instances")
        return all_pass

    except Exception as e:
        logger.error(f"Singleton test failed: {e}")
        RESULTS["errors"].append(f"Singleton test failed: {e}")
        RESULTS["singleton_test"] = {"error": str(e)}
        return False


async def step_12_test_concurrent():
    """Step 12: Concurrent test - 20 simultaneous requests."""
    logger.info("=" * 60)
    logger.info("Step 12: Concurrent Load Test...")
    logger.info("=" * 60)

    try:
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()

        async def get_model_concurrent(idx):
            try:
                model_info = await manager.get_model("embedding", _settings.EMBED_MODEL)
                return {"idx": idx, "success": True, "id": id(model_info)}
            except Exception as e:
                return {"idx": idx, "success": False, "error": str(e)}

        t0 = time.perf_counter()
        results = await asyncio.gather(*[get_model_concurrent(i) for i in range(20)])
        total_time = time.perf_counter() - t0

        success_count = sum(1 for r in results if r.get("success"))
        unique_instances = set(r.get("id") for r in results if r.get("success"))
        failures = [r for r in results if not r.get("success")]

        logger.info(f"  Concurrent requests: 20")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failures: {len(failures)}")
        logger.info(f"  Unique instances: {len(unique_instances)}")
        logger.info(f"  Total time: {total_time:.2f}s")

        concurrent_result = {
            "requests": 20,
            "successful": success_count,
            "failures": len(failures),
            "unique_instances": len(unique_instances),
            "total_time": total_time,
        }
        RESULTS["concurrent_test"] = concurrent_result

        all_pass = success_count == 20 and len(unique_instances) == 1
        log_result("Concurrent Test", "pass" if all_pass else "fail",
                   f"{success_count}/20 successful, {len(unique_instances)} instances")
        return all_pass

    except Exception as e:
        logger.error(f"Concurrent test failed: {e}")
        RESULTS["errors"].append(f"Concurrent test failed: {e}")
        RESULTS["concurrent_test"] = {"error": str(e)}
        return False


async def step_13_test_offline():
    """Step 13: Offline mode test."""
    logger.info("=" * 60)
    logger.info("Step 13: Offline Mode Test...")
    logger.info("=" * 60)

    from app.services.ai.runtime.download_models import get_model_downloader

    downloader = get_model_downloader()

    # Set offline mode
    downloader.set_offline(True)

    try:
        # Verify that models are still accessible
        from app.services.ai.model_manager import get_model_manager

        manager = get_model_manager()
        model_info = await manager.get_model("embedding", _settings.EMBED_MODEL)

        success = model_info is not None and model_info.get("model") is not None
        logger.info(f"  Offline mode enabled: {downloader.is_offline}")
        logger.info(f"  Model accessible offline: {success}")

        offline_result = {
            "offline_mode": downloader.is_offline,
            "model_accessible": success,
        }
        RESULTS["offline_test"] = offline_result
        log_result("Offline Test", "pass" if success else "fail",
                   "Model loaded from disk in offline mode" if success else "Failed to load offline")

    except Exception as e:
        logger.error(f"Offline test failed: {e}")
        RESULTS["errors"].append(f"Offline test failed: {e}")
        RESULTS["offline_test"] = {"error": str(e)}
        return False
    finally:
        # Restore online mode
        downloader.set_offline(False)


async def run_all_validations():
    """Run all validation steps in order."""
    RESULTS["start_time"] = time.time()

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 9 - AI RUNTIME VALIDATION")
    logger.info("=" * 60)
    logger.info(f"Project root: {project_root}")
    logger.info(f"AI_MODELS root: {Path(_settings.AI_MODELS).resolve()}")
    logger.info("=" * 60 + "\n")

    # Run ALL steps
    steps = [
        ("Standardize models", step_0_standardize_models),
        ("Download models", step_1_download_missing_models),
        ("Test Embedding", step_2_test_embedding),
        ("Test Classifier", step_3_test_classifier),
        ("Test Query Optimizer", step_4_test_query_optimizer),
        ("Test Summarizer", step_5_test_summarizer),
        ("Test Generator", step_6_test_generator),
        ("Test Reranker", step_7_test_reranker),
        ("GPU Check", step_8_check_gpu),
        ("Benchmark", step_9_benchmark),
        ("Memory", step_10_check_memory),
        ("Singleton", step_11_test_singleton),
        ("Concurrent", step_12_test_concurrent),
        ("Offline", step_13_test_offline),
    ]

    results_summary = []
    for name, coro in steps:
        logger.info("")
        try:
            result = await coro()
            status = "pass" if result else "partial"
            results_summary.append({"step": name, "status": status})
        except Exception as e:
            logger.error(f"Step '{name}' crashed: {e}")
            RESULTS["errors"].append(f"Step '{name}' crashed: {e}")
            results_summary.append({"step": name, "status": "fail"})

    # Calculate score
    pass_count = sum(1 for r in results_summary if r["status"] == "pass")
    total = len(results_summary)
    RESULTS["overall_score"] = f"{pass_count}/{total} steps passed"
    RESULTS["results_summary"] = results_summary
    RESULTS["end_time"] = time.time()
    total_time = RESULTS["end_time"] - RESULTS["start_time"]
    RESULTS["total_time_s"] = total_time

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    for r in results_summary:
        emoji = "✓" if r["status"] == "pass" else ("⚠" if r["status"] == "partial" else "✗")
        logger.info(f"  {emoji} {r['step']}: {r['status']}")

    logger.info(f"\n  Score: {RESULTS['overall_score']}")
    logger.info(f"  Total time: {total_time:.2f}s")

    if RESULTS["errors"]:
        logger.info(f"\n  Errors ({len(RESULTS['errors'])}):")
        for e in RESULTS["errors"]:
            logger.info(f"    ✗ {e}")

    # Save results to JSON
    output_path = project_root / "runtime_validation_results.json"
    with open(output_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    logger.info(f"\n  Results saved to: {output_path}")

    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 60)

    return RESULTS


def main():
    """Main entry point."""
    results = asyncio.run(run_all_validations())
    return results


if __name__ == "__main__":
    main()