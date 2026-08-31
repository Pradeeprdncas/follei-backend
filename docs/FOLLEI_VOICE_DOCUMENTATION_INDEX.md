# Follei Voice AI Documentation

This page is the entry point for Follei Tamil/Tanglish voice development.

## Read in this order

1. `FOLLEI_PROJECT_AND_VOICE_HANDOVER_2026-08-31.md`
   - Current platform and voice architecture.
   - What is complete, partial, and not built.
   - Current deployment and verification state.
2. `FOLLEI_VOICE_AI_TRAINING_AND_RUNTIME_SPEC.md`
   - Authoritative model roles, runtime contracts, training stages, latency budget, concurrency, and coding-agent rules.
3. `FOLLEI_VOICE_RECORDING_AND_DATASET_GUIDE.md`
   - Exact speaker, room, microphone, performance, transcript, consent, and dataset requirements.
4. `../voice_training/README.md`
   - Executable ingestion, validation, IndicF5 benchmark, F5 export, and model-server commands.

## Current model decision

- Tamil zero-shot baseline: `ai4bharat/IndicF5` at a pinned Hugging Face revision.
- Alternative training research: upstream `SWivid/F5-TTS`, tracked as a separate experiment unless IndicF5 checkpoint/tokenizer compatibility is proven.
- Current STT: ElevenLabs in the implemented live-call path.
- Current grounded generation: Follei worker/RAG generation pipeline with Tanglish response policy.
- Current production voice profile: none; no custom voice has been trained or approved.

## Target sequence

```text
owned 10-30 second reference
  -> IndicF5 baseline
  -> Tamil listener evaluation
  -> 30-60 minute purpose-recorded pilot
  -> conversational Tamil adaptation research if required
  -> 3-6 hour owned speaker corpus
  -> consented voice adaptation
  -> one-call and ten-call deployment tests
```

Do not begin large-scale video processing until the small baseline and pilot dataset have proven the text format, evaluation suite, and training path.
