COSMIC VALUES AUTO-RAP — Roblox Pet Simulator 99

WHAT IS ALREADY CHANGED
- PetSimulator99_CV_AutoRAP_Flying_Icons.rbxl was patched from your latest Gargantuan flying/icon build.
- Arcade's central server price lookup first uses Cosmic Values RAP from a JSON cache.
- Missing exact variant RAP uses deterministic estimates; these are NOT official Cosmic Values prices.
- The old hardcoded Pet99Prices values are used only as fallback estimates, no longer treated as verified.
- Color Dice, Upgrader, Coinflip, inventory RAP and other Arcade calls using this same lookup read the shared cache.
- No pet models, ride scripts, or flying/icon assignments were edited.

ONE-TIME SETUP REQUIRED FOR LIVE CV PRICES
1. Upload this package's updater service to a Python-capable hosting service with PUBLIC HTTPS.
   Use requirements.txt and Procfile. Start command: python cv_updater.py
   Install dependencies: pip install -r requirements.txt
   Set environment variable PORT if your host needs it.
2. Make sure the website permits your automated access. This is an UNOFFICIAL website parser, not an API.
   Start with CV_MAX_PAGES=3 for a small test. Increase only if authorized and needed.
   The updater checks the website at most every 30 minutes (default); pauses >=2 s between pages.
3. Verify https://YOUR-HOST/health shows status ok with a nonzero count.
   Verify https://YOUR-HOST/api/rap returns JSON with items such as "huge cat" and "golden|huge cat".
   Ensure it correctly matches current CV prices before enabling.
4. Open PetSimulator99_CV_AutoRAP_Flying_Icons.rbxl in Roblox Studio.
   Search all scripts for: CV_RAP_ENDPOINT
   Change: https://YOUR-DEPLOYED-DOMAIN.example/api/rap
   to your real public HTTPS URL.
5. Game Settings > Security > Enable HTTP Requests.
6. Run in Studio with server output visible; look for [CV RAP] updated.
   Existing servers poll the endpoint every 5 minutes (not instant).

SAFETY & LIMITATIONS
- As of writing, there is no confirmed official Cosmic Values API or verified live scraping selector.
  CV's site can change HTML/pagination, so check the parser output and website terms before deployment.
- This environment cannot contact the CV website directly to end-to-end verify the updater.
- The updater retains the last successful on-disk cache on upstream failures.
- If live feed is absent/unavailable, Arcade prices are still usable but are estimated.
- If the cached website data is older than a day, the Roblox game refuses to overwrite its last downloaded in-memory cache.
- CV prices include Normal/Golden/Rainbow where present; Shiny variants get an estimated multiplier when not listed.
- Estimates should be clearly labeled in Arcade UI; some older UI labels still mention the historical Pet99Prices data.
- This is for a personal private Roblox game; do not imply the estimates are official CV RAP.
