# Local operations and optional intake

## Helper

`scripts/workflow.py` requires Python 3.10+, plus FFmpeg/ffprobe on PATH to attach media. It uses the standard library. IANA timezones use OS data; Windows may need optional `tzdata`. No renderer, AI model, Drive client, uploader, or scheduler is bundled.

Use a separate project root; paths below are examples:

```sh
python /path/to/skill/scripts/workflow.py --root /path/to/project init
# Edit the generated workflow.json before creating actual jobs.
python /path/to/skill/scripts/workflow.py --root /path/to/project create demo --title "A useful shortcut" --brief "Show a real task and its result."
python /path/to/skill/scripts/workflow.py --root /path/to/project start demo
# Render and review actual media using available creative tools.
python /path/to/skill/scripts/workflow.py --root /path/to/project video demo --path media/demo-v1.mp4 --final --approval-reference "User approved this final version in the current chat"
python /path/to/skill/scripts/workflow.py --root /path/to/project assets demo --caption assets/demo-v1.txt --cover assets/demo-v1.png --qa assets/demo-qa.json
python /path/to/skill/scripts/workflow.py --root /path/to/project verify demo
python /path/to/skill/scripts/workflow.py --root /path/to/project show demo
```

`start` is optional for imported finals. `video` requires an approval/policy reference, checks decode, and rejects duplicate hashes/exclusions. `assets` checks video integrity, caption size/required tags, cover dimensions, and QA attestation. Neither establishes rights, creative quality, authorization, or live eligibility.

Mutable state is `.video-workflow/state.json`. An OS file lock serializes mutations and same-directory temporary writes are atomically replaced. Paths must be regular nonempty files inside the project, without traversal/symlinks/reparse points. Do not hand-edit active state. Use project-local `media/`, `assets/`, and `evidence/` directories.

Other commands (`--help` gives arguments):

- `exclude --path media/old.mp4 --reason "Already published"`: record an exclusion hash.
- `slot JOB PLATFORM --after ISO_TIMESTAMP`: suggest a slot after the verified live queue end. Inspect the full online queue too.
- `begin-submit JOB PLATFORM --at ISO_TIMESTAMP`: persist an attempt before submission. Requires enabled publishing and a nonempty authorization reference in the job's profile snapshot; these remain records, not permission grants.
- `confirm JOB PLATFORM --attempt ID --post-id ID --account ACCOUNT --at ISO_TIMESTAMP --visibility public --evidence evidence/post.json`: record a verified result.
- `reconcile-absent JOB PLATFORM --attempt ID --evidence evidence/absence.json`: record absence before a deliberate retry.
- `handoff JOB --stage assets --state sending --reference DESTINATION`: record dispatch intent; follow with `--state sent --reference MESSAGE_ID` after success. Stages: `assets`, `publisher`. Inspect uncertain delivery before retrying.

Evidence files are UTF-8 JSON with timezone-aware `observed_at`, `observer`, and `note`. Confirm evidence also contains `post_id`, `account`, `scheduled_at`, `visibility`. Absence evidence contains `absent: true`, `account`, and `checked: ["scheduled", "published", "drafts"]`. These report an observer's facts; the helper cannot establish online truth from a fabricated report.

Each job snapshots its profile. Configure actual accounts and authorization before creating jobs; later config edits cannot silently retarget them. Version one supports one video per day per platform/account and rejects other daily caps.

Aggregate states are `planned → producing → awaiting_assets → ready → publishing → scheduled`. The production stage is optional for imports. `publishing` includes partial success and uncertain attempts; inspect the per-platform records to determine what remains. Reconciled absence can restore `ready` when all targets are ready. All-target completion alone reaches `scheduled`.

For offline trials, use `init --simulation` in a separate root. The ledger and each job expose `execution_mode: simulation`. All platform IDs, accounts, evidence and results in that project are fixtures; never perform real publishing or messaging from it. The helper has no network actions in either mode. A normal project is labeled `live-recording` to distinguish actual observations from test evidence.

For timezones with daylight saving, ambiguous/nonexistent daily times are rejected on the affected date. Choose an unambiguous schedule rather than silently shifting a post.

For example, a configured `publish.platforms` object can be `{"instagram": "@your-brand", "tiktok": "@your-brand"}`. Replace these with exact accounts you control. Keep `enabled` false until publishing is authorized, then record the actual instruction in `authorization_reference`. These fields are local records, not platform credentials. Select an IANA timezone such as `Europe/London` or `Asia/Kuala_Lumpur` for your own schedule.

## Optional folder intake

Use a provider connector; do not bundle tokens or assume a connection exists. This procedure works for Drive or another store with stable IDs/versions.

1. Establish folder, frequency/timezone, local destination, and whether uploads count as final approval. Baseline existing files; name/size matches are weaker than downloaded hashes.
2. Maintain a project-local ledger of provider ID/version, size, downloaded hash/path, job ID, completed stage, dispatch state, and last error. Read every page of direct children. Incomplete listing cannot establish "no new files". Never persist signed download URLs.
3. Acquire a persistent run lease with run ID, expiry, and refreshed heartbeat, protected by a short file lock. Recover expired runs from actual files/jobs. A lock held by one short command is not a cross-tool lease.
4. Download configured video types to `.part` staging via authenticated raw-download tools. Sanitize basenames and reject traversal/reserved names. Check byte count, video probe, full decode and hash. Refetch an expired reference once; stop for auth/permission failures.
5. Deduplicate against intake, existing content, exclusions and jobs. Changed known IDs or same filename/different bytes need review. Identical bytes under a new ID are duplicate content. Never overwrite or silently republish revisions.
6. Atomically promote without overwrite, create a stable job ID, attach the video under the authorized approval policy, and continue assets/publishing. Persist progress at every stage so downloads cannot strand later work.
7. Resume unfinished stages first. Preserve source contents/scheduled files. Notify only meaningful progress, failure, or required input.

The helper does **not** implement the provider adapter or persistent lease. The host agent must implement and operate them before promising unattended intake.

## Recurring runs

When requested, inspect existing automations with the host's scheduling tool; update/create one monitor rather than duplicates. Its prompt loads project instructions/profile, resumes incomplete work, acquires leases, inspects intake, and performs only authorized stages. Keep secrets in authenticated connections.

State the host accurately. Local schedules may require the computer awake, app running, network, files, and browser login. Hosted runners need explicit setup and credentials. Installation/a schedule entry proves neither unattended operation nor publishing success. Verify a real run before claiming it works unattended.
