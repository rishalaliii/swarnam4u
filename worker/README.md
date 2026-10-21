# Optional fastest path (recommended)
1. Cloudflare dashboard > Workers & Pages > Create Worker > paste `rates-worker.js` > Deploy (free plan is enough).
2. Copy the worker URL into `var WORKER="..."` near the top of the live-fetching section in `assets/site.js`.
The worker fetches AKGSMA and the backup pages from Cloudflare's network and caches for 30 s, so every visitor gets the answer from a nearby cache in well under a second.
