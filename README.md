# Anas Content Factory

**Anas Content Factory (ACF)** is a local-first, autonomous video post-production engine.

> Give ACF a folder and let it figure out the production.

The design principle is simple: **AI decides. Deterministic tools execute. Verification checks the result.**

ACF does not require n8n, Claude Code, HyperEdit, Remotion, Obsidian, a database, or a giant local model.

The intended user experience is simple:

    acf run "D:/Videos/ClientProject"

The system discovers the media, prepares lightweight analysis assets, normalizes a timestamped transcript when Whisper is available, samples frames for vision analysis, asks a cloud model to create an executable edit plan, renders a review build, creates Shorts, runs technical QC, and delivers configured outputs.

The laptop is the deterministic workstation. Large semantic models do not need to run locally.

## Architecture

    RAW FOLDER
        |
        v
    DISCOVER / ANALYZE
        |
        +-- manifest / proxies / audio / silence
        |
        v
    TRANSCRIBE
        |
        v
    VISUAL ANALYSIS + MEDIA INDEX
        |
        v
    PRODUCER / DIRECTOR AI
        |
        +-- edit plan / style / motion beats / Shorts
        |
        v
    FFMPEG EDITOR
        |
        v
    REVIEW + VISUAL VERIFY
        |
        v
    APPROVAL
        |
        +----------+----------+
        v                     v
      MASTER                 SHORTS
        |                     |
        +----------+----------+
                   v
                  QC
                   |
                   v
               DELIVERY

## Pipeline

1. Discover
   - Finds supported video, audio and image assets recursively.
   - Records FFprobe metadata in analysis/media-manifest.json.
   - Does not copy or modify the originals.

2. Analyze
   - Creates lightweight 1280px proxies.
   - Extracts mono 16 kHz working audio.
   - Runs a lightweight FFmpeg silence scan and stores analysis/silence.json.
   - Keeps long media streamed through FFmpeg instead of loading it into RAM.

3. Transcribe
   - Optional local Whisper/whisper.cpp.
   - Normalizes different Whisper JSON shapes into analysis/transcript.json.
   - Produces analysis/transcript.md and SRT-ready timestamps.
   - Missing transcription is treated as a degraded capability, not an automatic failure.

4. Visual analysis
   - Selects a bounded number of frames from proxies.
   - Sends only selected frames to the configured vision model.
   - Stores analysis/scenes.json and analysis/assets.json.
   - Builds analysis/media-index.json so local assets and visual discoveries can be searched without a database.

5. Plan
   - Producer/Director model receives the manifest, transcript, visual analysis, silence analysis and references.
   - Selects a built-in editing style such as clean, short-form, course or showreel.
   - May create sparse timestamped motion beats for important spoken moments.
   - Produces decisions/edit-plan.json.
   - Plans are timestamped and inspectable before rendering.
   - Project style feedback is retained in analysis/style-memory.md after natural-language revisions.
   - Project category folders are created only after the category is inferred.

6. Execute
   - Deterministic FFmpeg segment renders.
   - Supports trims, joins, reframing, transcript captions, sparse motion beats/callouts, explicit graphics and audio normalization.
   - Segment checkpoints make interrupted renders resumable.
   - Motion-beat data is included in the segment cache key so visual changes re-render correctly.

7. Review
   - Produces a lightweight review/review.mp4.
   - Writes review/review-notes.md with the checks to perform.
   - Runs sampled-frame visual verification and stores review/verification.json.
   - When review_required_before_final is enabled, the pipeline pauses here until acf review PROJECT --approve.
   - Revisions can be requested in natural language and restart only the downstream stages.

8. Shorts
   - Clip Hunter analyzes transcript chunks instead of repeatedly sending the entire transcript.
   - The fast `acf clips` command skips full master/review production when only Shorts are needed.
   - Candidates are scored for hook strength, standalone clarity, usefulness, pacing and related editorial signals.
   - Overlapping candidates are deduplicated before selection.
   - Each candidate is rendered independently in 9:16 with captions when timestamped transcript data exists.
   - Candidates and their timestamps are stored in decisions/shorts-candidates.json.

9. QC
   - Checks file existence and size.
   - FFprobe checks duration, streams, dimensions and frame rate.
   - FFmpeg decode check catches corrupt outputs.
   - Audio checks catch silence and clipping.
   - Black-frame checks catch long unexpected black spans.
   - Caption metadata is checked when captions were requested.
   - Final delivery expectations are checked after delivery starts.

10. Delivery
    - Master 1080p render is the canonical intermediate.
    - Configured profiles are transcoded into delivery/.
    - A final post-delivery QC is run before the job reaches COMPLETED.

## CLI

Start a full autonomous production run:

    acf run "D:/Videos/Project"

Run the fast Shorts-only pipeline:

    acf clips "D:/Videos/Project"

Add a supplied reference URL:

    acf run "D:/Videos/Project" --reference "https://example.com/reference"

Inspect a job:

    acf status Project

Resume after interruption or a resolved human-action request:

    acf resume Project

Show a pending human question or the review location:

    acf review Project

Approve the review build and continue:

    acf review Project --approve

Resolve a pending question and continue:

    acf review Project --answer "Use the second camera from 01:12 to 01:26."

Run deterministic fast actions without asking an AI model to reason through the mechanical operation:

    acf action Project "remove dead air"
    acf action Project "add captions"
    acf action Project "create shorts"

Run a standalone visual verification pass:

    acf verify Project

Search the local project media index:

    acf assets Project "Claude logo"

Request a natural-language edit revision:

    acf revise Project "Tighten the intro and remove the repeated explanation around the middle."

Run QC directly:

    acf qc Project

Check the local runtime before handing the laptop to the factory:

    acf doctor

Deliver configured final outputs:

    acf deliver Project

## Job layout

Each job uses:

    jobs/PROJECT/
        project.json
        source/
        analysis/
        assets/
        decisions/
        working/
        review/
        exports/
        delivery/

Required analysis files include:

- summary.md
- transcript.md
- transcript.json
- scenes.json
- speakers.json
- highlights.json
- issues.json
- assets.json
- media-manifest.json
- media-index.json
- silence.json
- style-memory.md (created when useful style feedback is learned)
- references.md

The project state tracks stage attempts, completion, errors, warnings, outputs, human-action requests and resumability.

## Editing styles

ACF intentionally uses a small style system rather than a giant external skills framework.

Built-in styles:

- clean — restrained professional/talking-head editing
- short-form — faster social editing
- course — educational content focused on comprehension
- showreel — higher-energy promotional/event editing

The Producer chooses a suitable style from the project type and can use project-specific feedback stored in analysis/style-memory.md.

Motion beats are deliberately lightweight: short, timestamped callouts or emphasis text rendered by FFmpeg. ACF is not trying to become a full browser timeline or a Hyperframes/Remotion clone.

## Export profiles

Built-in profiles are:

- review
- master_1080p
- youtube_1080p
- vertical_1080x1920
- square_1080

Aliases include youtube, shorts, reels, instagram-reel and square.

## Human escalation

The system should only ask when it is genuinely blocked, the input is materially ambiguous, or the configured review gate needs a human approval.

Questions are stored in decisions/human-action.json. The CLI shows the exact stage, reason, question and context. After the answer is supplied, acf resume retries from the interrupted stage rather than restarting the whole job.

## Project memory and verification

Project feedback is stored as plain text instead of a database:

    analysis/style-memory.md

This lets later planning remember practical preferences such as cleaner overlays, stronger openings, less motion, or keeping graphics away from the speaker.

Visual verification samples the rendered review and asks the vision provider to look for concrete production defects such as clipped text, broken crops, black frames, accidental UI or overlays covering important content.

Verification is intentionally conservative: subjective artistic taste is not automatically treated as a failure.

## Resource policy

- Original media is treated as immutable.
- Long media is processed with FFmpeg streaming operations.
- Analysis uses low-resolution proxies and selected frames.
- The semantic model receives metadata, transcript text and selected frames instead of entire source files by default.
- Maximum media concurrency is one job at a time.
- No account rotation or quota-abuse logic is included.

## Setup

Requirements:

- Python 3.10+
- FFmpeg and FFprobe on PATH
- Optional whisper-cli plus a local model file
- A Gemini API key or OpenRouter API key for semantic planning and vision

Install:

    python -m pip install -e .

Copy .env.example to .env and fill only the providers you actually use.

Never commit .env, source media, generated jobs or model weights.

## Engineering status

Package version: 0.3.0

Implemented:

- autonomous project orchestration
- media discovery and FFprobe manifests
- lightweight proxies and working audio
- Whisper transcript normalization
- visual frame analysis
- searchable project media index
- Producer/Director planning
- deterministic FFmpeg execution
- smart silence analysis
- deterministic fast actions
- Clip Hunter and Shorts generation
- built-in editing styles
- project style memory
- timestamped motion beats
- review renders
- sampled-frame visual verification
- human approval gate
- natural-language revisions
- technical QC
- final delivery

Current validation status:

The repository has not yet been validated against real client media on the target laptop from this environment. The next engineering step is real-world testing and tuning around FFmpeg edge cases, transcription quality, provider responses, motion-beat readability and editorial output quality.

The long-term UX remains:

    Give it a folder
          |
          v
      Let it work
          |
          v
    Review when required
          |
          +----> Approve or revise
          |
          v
      Get the outputs
