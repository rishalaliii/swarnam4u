# Swarnam4U cloud Shorts pipeline — next steps

This branch starts safely. It does not change your website, current rates, or existing update workflow.

1. Open Actions and run **Swarnam4U Shorts Preflight** manually.
2. If it fails due to a stale board date, that is the correct safeguard. Do not edit timestamps or copy yesterday's prices forward.
3. If it passes, review the artifact `swarnam4u-shorts-preflight`.
4. Next implementation steps are: add a tested bilingual script/scene generator; add neural TTS; render videos with FFmpeg; inspect all six artifacts; then configure YouTube OAuth/secrets and private/unlisted upload tests.
5. Keep publish disabled until real rate parsing, Malayalam pronunciation, rendered text, video/audio integrity, idempotency, and YouTube authorization have been verified.

Target timetable: 10:00, 13:00, 17:00 IST for English and Malayalam. Cron schedule is UTC conversion and is not guaranteed to run to the exact minute.

Critical data rules:
- AKGSMA current board date must match Asia/Kolkata current date.
- Do not publish if the board has not published today's rates.
- Use the board's silver 925 price only when it is actually published; otherwise omit 925 or mark a displayed calculation as calculated.
- Clearly label calculated 24K/14K rates; AKGSMA's stated board values used here are 22K/916, 18K/750, and silver 999.
