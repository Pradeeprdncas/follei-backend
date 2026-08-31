# Follei Tamil TTS training workspace

This directory separates dataset preparation, model evaluation, training, and serving from the Follei backend. Audio, checkpoints, and generated outputs are ignored by Git.

The authoritative end-to-end architecture, runtime contract, latency budget, lead-nurturing flow, and coding-agent rules are documented in `docs/FOLLEI_VOICE_AI_TRAINING_AND_RUNTIME_SPEC.md`.

## Current model decision

Use `ai4bharat/IndicF5` first as the Tamil zero-shot baseline. It supports Tamil and accepts target text, reference audio, and the exact reference transcript. Its model files are gated on Hugging Face and require accepting the model terms. AI4Bharat has not published an official IndicF5 fine-tuning recipe, so do not load its checkpoint into upstream F5-TTS unless checkpoint and tokenizer compatibility has been verified.

If zero-shot evaluation is insufficient, run a separate upstream `SWivid/F5-TTS` fine-tuning experiment using its official custom-dataset tooling. Treat that as a new experiment, not as an IndicF5 fine-tune.

## Hardware

Do not train on the current Intel Mac. Use a Linux CUDA machine with at least 24 GB GPU memory for the initial experiment, 100 GB free persistent storage, and Python 3.10 or 3.11. Keep source audio and checkpoints in private object storage.

## 1. Collect approved recordings

Use purpose-recorded speech from an owned or explicitly licensed speaker. For any external source, retain the signed license and record it in `manifests/sources.jsonl`. `rights_confirmed` must be `true` before a clip can enter training.

Record 24-bit or 16-bit mono WAV in a quiet, treated room. Capture 30-60 minutes for the first adaptation experiment and 3-6 hours for a production voice. Include neutral, support, sales, empathy, questions, code-mixed English, names, phone numbers, dates, currency, GST, EMI, KYC, OTP, URLs, and product names.

## 2. Prepare clips

Install FFmpeg and the data dependencies on the processing machine:

```bash
python -m venv .venv-data
source .venv-data/bin/activate
pip install -r requirements-data.txt
```

Standardize each accepted clip to mono, 24 kHz, 16-bit PCM:

```bash
ffmpeg -i input.wav -ac 1 -ar 24000 -sample_fmt s16 output.wav
```

For licensed video material only, use `yt-dlp` to extract audio and Demucs to isolate vocals. Then apply VAD, speaker filtering, overlap/music rejection, ASR draft transcription, and human transcript correction. Demucs output is never automatically accepted as training data.

Run controlled ingestion from the provenance manifest:

```bash
python scripts/ingest_sources.py manifests/sources.jsonl data --dry-run
python scripts/ingest_sources.py manifests/sources.jsonl data --separate-vocals
```

Create `manifests/clips.jsonl` using `manifests/clips.example.jsonl` as the schema. Use source-level splits: recordings from one session must not be scattered across train and test.

Validate before spending GPU time:

```bash
python scripts/validate_manifest.py manifests/clips.jsonl
```

The validator requires approved provenance, exact transcripts, 2-12 second mono 24 kHz PCM clips, unique paths, and train/validation/test splits.

## 3. Benchmark IndicF5 before training

Accept the model terms at `https://huggingface.co/ai4bharat/IndicF5`, authenticate with `hf auth login`, and pin the model commit SHA. Run on a CUDA machine:

```bash
python -m venv .venv-inference
source .venv-inference/bin/activate
pip install -r requirements-inference.txt
pip install git+https://github.com/AI4Bharat/IndicF5.git

python scripts/benchmark_indicf5.py \
  --reference-audio /data/references/owned_voice.wav \
  --reference-text 'REFERENCE TRANSCRIPT IN EXACT TAMIL/MIXED SCRIPT' \
  --prompts eval/prompts.jsonl \
  --output-dir outputs/indicf5-baseline \
  --revision MODEL_COMMIT_SHA
```

Have at least three Tamil listeners rate every sample from 1-5 for intelligibility, naturalness, accent, speaker similarity, emotional fit, and business-entity pronunciation. Keep the reference voice constant while comparing models.

Connect the accepted baseline to Follei:

```bash
export TTS_MODEL_REVISION=MODEL_COMMIT_SHA
export TTS_REFERENCE_AUDIO=/data/references/owned_voice.wav
export TTS_REFERENCE_TEXT='EXACT REFERENCE TRANSCRIPT'
export TTS_API_KEY='PRIVATE_INTERNAL_TOKEN'
uvicorn server:app --host 0.0.0.0 --port 8090
```

Then set `TTS_PROVIDER=follei`, `FOLLEI_TTS_BASE_URL=http://GPU_HOST:8090`, and the matching `FOLLEI_TTS_API_KEY` in the backend environment.

## 4. Prepare an upstream F5 experiment

Export the officially documented `audio_file|text` CSV with absolute paths:

```bash
python scripts/build_f5_csv.py manifests/clips.jsonl outputs/follei_tamil_train.csv
```

On the GPU machine, install the current upstream repository at a pinned commit and run its preparation command:

```bash
git clone https://github.com/SWivid/F5-TTS.git
cd F5-TTS
git checkout PINNED_COMMIT_SHA
pip install -e .

python src/f5_tts/train/datasets/prepare_csv_wavs.py \
  /workspace/voice_training/outputs/follei_tamil_train.csv \
  /workspace/F5-TTS/data/follei_tamil
```

Tamil requires a tokenizer/vocabulary compatible with both the selected pretrained checkpoint and the dataset. Do not start a fine-tune until a dry-run confirms every Tamil and Latin character is represented. The upstream default checkpoint is not a proven replacement for IndicF5 Tamil capability.

## Promotion gates

A checkpoint can become `tamil-prosody-v1` only when it beats the baseline on a held-out test set, has no training/test source overlap, correctly handles the entity suite, has documented voice consent, and passes a ten-call load test. Voice identity adaptation happens only after the Tamil/prosody checkpoint passes these gates.
