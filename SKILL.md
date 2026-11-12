---
name: video-content-workflow
description: "Take short-form content from an idea through video production, verified captions and covers, and an authorized publishing handoff. Use for a complete video content pipeline or resuming its stages, including optional folder intake; use a dedicated editor for an isolated editing task."
---

# Video Content Workflow

Produce content for the user's audience, then hand off immutable final assets with enough evidence to resume safely. Installed creative tools and connected services perform rendering, image generation, downloads, and publishing; this skill coordinates them.

## Choose the entry and stopping point

- **Idea:** develop the concept and produce the video when production is requested.
- **Script/project:** continue the approved direction and preserve existing edits.
- **Final video/approved intake folder:** inspect the actual file and continue with caption and cover.
- **Existing job:** inspect the ledger, assets, and live platform records before resuming.

Stop at the requested scope. Ideas, scripts, alternatives, or previews do not authorize publishing. Existing standing authorization can cover later handoffs; avoid repeated per-item permission requests within that scope. Installation does not authorize messaging, paid generation, recurring tasks, or public posts.

## Set the project profile

Read project instructions and brand files first. Capture missing decisions in a project-local `workflow.json`: audience, language, goal, content type, style, tools, review policy, platforms/accounts, timezone/schedule, and permitted handoffs. Adapt [assets/profile.example.json](assets/profile.example.json); its dimensions and times are examples, not universal defaults.

Use a separate project directory for runtime data. Keep private media, credentials, signed download URLs, and chat IDs outside the installed skill. The helper is `scripts/workflow.py`; paths are relative to the chosen project root. Read [references/operations.md](references/operations.md) when using it, optional intake, or recurring runs.

## Create the video

Read [references/production.md](references/production.md) for planning, production, and final checks. Choose a format that fits: product demonstration, tutorial, story, interview, educational clip, or another requested form. Movie education is one optional [example](references/examples.md).

Use an available editor, renderer, recording tool, or generation tool. Discover actual capabilities; do not assume a named editor or paid model is installed. Deliver a playable video and editable project when available. A script or placeholder does not satisfy a request for a finished video.

Record the factual brief, sources/rights status, existing audio, important dialogue/time ranges, and uncertainty. Inspect frames throughout the timeline and listen to the audio. Full decode is an additional technical check, not a substitute. Honor explicit final-review requirements; an already-authorized direct-completion/intake policy can satisfy the gate without another question.

## Create caption and cover

Read [references/assets.md](references/assets.md). Inspect the final video rather than relying on filenames or an old script. Write a caption-only UTF-8 file and create a versioned final cover using the project's language and style. Check current target crops and thumbnail readability. Do not force movie names, Chinese copy, cinematic imagery, or a fixed ratio onto unrelated projects.

Verify the video, caption, and cover together and record QA observations. Freeze SHA-256 values only after review. Changed bytes invalidate the handoff; preserve scheduled versions. The helper checks integrity and transitions, not truth, taste, or whether someone actually listened.

## Hand off and publish within authorization

Read [references/publishing.md](references/publishing.md) for scheduling/handoffs. One chat can perform the stages; multiple existing chats are optional. Message only authorized destinations. Include job ID, absolute project/asset paths and hashes, factual brief, unresolved issues, and next action. Do not make the user shuttle files between already-authorized workers.

Only one publisher controls a platform/account at a time. Read live scheduled posts, published posts, and drafts before slot selection or retries. Track platforms independently. Persist an attempt **before** submitting. An uncertain result remains unresolved until live reconciliation; never blindly upload again. Local `ready` is not proof of scheduling.

Offline trials use a separate root initialized with `--simulation`. Jobs marked `execution_mode: simulation` must never trigger real messages, uploads, or public posts; label their results as fixtures.

Reversible production and read-only planning can proceed within the task. Public posting must match current or standing user authorization. A config checkbox is not that authorization. Keep drafts out of submission and preserve existing exclusions/scheduled posts.

## Optional intake and recovery

Use the intake procedure in [references/operations.md](references/operations.md) only with a configured source. Folder uploads mean final approval only if the user chose that policy. Deduplicate by provider ID/version and downloaded hash; name/size matches are weaker evidence. Resume unfinished stages first.

For recurring execution, inspect existing monitors with the host's automation tool and avoid duplicate dispatchers. Document whether execution is local or hosted and what must remain available. Do not claim always-on operation from a schedule entry. Notify on progress, failure, or required input; unchanged scans can remain quiet.
