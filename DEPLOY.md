# Deploy Forge to Render (always-on, use it from any device)

Forge runs as **one Docker web service**: FastAPI serves both the API and the
built frontend. No separate frontend host needed.

## Steps
1. **Put `forge/` in a GitHub repo** (its own repo is cleanest), and push it.
2. In **Render → New + → Blueprint**, connect that repo. Render reads
   `render.yaml` and configures the service automatically.
3. When prompted, set the secret **`ANTHROPIC_API_KEY`** to your `sk-ant-…` key
   (this is what powers prompts / Invent / patent prose / edit-by-chat).
4. Click **Apply / Deploy**. The first build takes ~8–12 min (it installs
   CadQuery/OpenCASCADE). Subsequent deploys are faster.
5. Open the Render URL — Forge is live. Bookmark it on your iPad/phone.

## Plan choice (in `render.yaml`)
- **`plan: starter`** (~$7/mo) — always-on + a 1 GB **persistent disk** at `/data`
  so your inventions and version history are saved across restarts. **Recommended.**
- **`plan: free`** — to try it. But: it **sleeps after 15 min** (slow ~30 s wake-up)
  and has **no persistent disk**, so saved projects reset on each restart/redeploy.
  To use free, change `plan: free` and delete the `disk:` block.

## Honest caveats on the cloud version
- **No PrusaSlicer in the cloud image** → print time/cost falls back to the rough
  estimate (your Mac, with PrusaSlicer installed, gives the real sliced numbers).
  A Linux slicer (CuraEngine) can be added to the image later.
- **Sandbox**: macOS `sandbox-exec` doesn't exist on Linux, so the AI-code worker
  runs with the container boundary + the static import-allowlist + restricted
  builtins + process timeouts (no kernel-level network-egress denial). Fine for a
  single-user tool; for multi-user, add a hardened container/seccomp profile.
- **Keep the URL private** (or add auth) — anyone with the link can use your
  Anthropic credits.
