# Anas Content Factory

An autonomous, local-first content post-production system.

## Intended workflow

Give it a path:

    acf run "D:\Videos\ClientProject"

It discovers the media, creates a job, probes the files, prepares lightweight analysis media, routes semantic planning to configured cloud AI, writes an inspectable edit plan and preserves state.

The laptop does not need to run a large language model.

## Architecture

- Producer/Director: understands the content and plans the edit.
- Editor/Finisher: executes the plan.
- FFmpeg/FFprobe: deterministic media operations.
- Lightweight transcription: local when installed.
- Gemini: primary semantic provider.
- OpenRouter: configurable fallback provider.
- Local jobs: never committed to Git.

## Setup

Requirements:
- Python 3.10+
- FFmpeg and FFprobe on PATH
- Optional whisper-cli for transcription
- A Gemini or OpenRouter API key

Install:

    python -m pip install -e .

Configure environment variables from .env.example.

Run:

    acf run "D:\Videos\Project"

Inspect:

    acf status Project
    acf plan Project
    acf qc Project

## Current milestone

The repository currently contains the core job lifecycle, media discovery/probing, proxy/audio preparation, provider routing, producer planning, state tracking and QC foundation.

The next milestone is full timestamped transcription ingestion and deterministic execution of edit-plan decisions into review/final renders.

Never commit source media, generated jobs or secrets.
