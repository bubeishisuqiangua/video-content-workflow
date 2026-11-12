# Caption and cover

Read the final video and brief. Distinguish exact speech, paraphrases, explanation, and product claims.

## Caption

Write in the audience's language and brand voice. Open with the scene, useful phrase, question, or concrete benefit delivered by the video. Add context and an appropriate next step. Avoid filler, fabricated quotes, unsupported results, and mandatory link pushing.

The final UTF-8 file contains only publishing copy: no filename, editor notes, fences, or scheduling instructions. Validate actual platform limits. The helper measures UTF-16 code units where configured; platform adapters enforce additional limits.

Hashtags are brand policy. A bilingual movie-learning brand may require separate Chinese and English title tags for each featured film. Verify real titles; prose does not replace required tags. Other brands use their own relevant taxonomy.

## Cover

Choose representative video frames, product imagery, illustration, or generated art suitable for the brief and permissions. A cinematic still is one option, not a required format.

Check the current target surfaces: video ratio, feed crop, profile thumbnail, and editor behavior can differ. Example dimensions are profile choices, not universal platform facts. Keep essential text inside the actual crop, and inspect the exported cover and thumbnail. A center-square preview can be an additional conservative check.

Use one readable idea with clear hierarchy. Inspect title spelling, contrast, edges, and small-size legibility. Preserve versioned outputs once handed off.

## QA report

Write `qa.json` reflecting actual observations:

```json
{
  "reviewer": "content-editor",
  "observed_at": "2026-01-15T10:00:00+00:00",
  "video_reviewed": true,
  "caption_reviewed": true,
  "cover_reviewed": true,
  "notes": "Inspected timeline and crop; listened to speech; checked claims and tags."
}
```

This is an attestation, not automated proof. Do not copy it and mark checks true without reviewing. `assets` freezes the report's hash with the trio. A revised pair uses new files; after any submission, use explicit revision handling rather than changing that job.
