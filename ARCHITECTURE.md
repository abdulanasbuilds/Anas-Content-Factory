# Anas Content Factory Architecture

Input path -> discovery -> media manifest -> local preparation -> transcription -> semantic analysis -> Producer -> inspectable edit plan -> Editor/FFmpeg -> review -> QC -> delivery.

## Resource model

The laptop handles discovery, FFprobe, FFmpeg, lightweight transcription, state and rendering. Cloud providers handle semantic reasoning. A large local language model is not required.

## Rules

1. Originals are immutable.
2. Never load a whole long video into Python memory.
3. Prefer streaming/chunked FFmpeg operations.
4. Generate low-resolution proxies for inspection.
5. Send transcripts, metadata and selected analysis artifacts to cloud models rather than entire originals by default.
6. Serialize heavy media operations on a 16 GB laptop.
7. Keep credentials out of Git.
8. Every stage writes state so jobs can resume.

This is the foundation for a production system; advanced visual understanding is implemented through replaceable provider/tool adapters.
