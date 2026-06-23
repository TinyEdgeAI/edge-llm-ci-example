# Edge LLM deployment, gated by CI

[![decide](https://github.com/TinyEdgeAI/edge-llm-ci-example/actions/workflows/decide.yml/badge.svg)](../../actions/workflows/decide.yml)
[![validate](https://github.com/TinyEdgeAI/edge-llm-ci-example/actions/workflows/validate.yml/badge.svg)](../../actions/workflows/validate.yml)

An example project that ships an on-device LLM (`Llama-3.2-1B`) to a **Jetson Orin Nano** — with [TinyEdge](https://tinyedge.ai) wired into CI so **every change is benchmarked on the real device before it ships.**

The badges above show the status of the two workflows; results for each run are in the [Actions tab](../../actions).

## What the CI does

The model and its budget are declared in [`model.yaml`](model.yaml). On top of that, two workflows run automatically:

| Workflow | Trigger | What it does |
|---|---|---|
| [**decide**](.github/workflows/decide.yml) | push to `main` | sweeps the quant ladder (`q8_0`, `q4_k_m`, …) on the Jetson, **picks the best variant** for the `max_quality` profile, and publishes an **Ed25519-signed deployment manifest** as a build artifact |
| [**validate**](.github/workflows/validate.yml) | pull request | benchmarks the candidate on the Jetson and **fails the PR** if it regresses past the latency/RAM/accuracy budget vs the baseline |

## See it for yourself

1. Open the **[Actions tab](../../actions)** → click the latest **decide** run → the summary shows the verdict, the variant chosen, and the measured perplexity/latency, with the **signed manifest** attached as an artifact.
2. The **validate** check is what runs on PRs — open one that tightens the budget and watch it go **red ✗** (a regression that would never reach a device).

On each change, CI reports — measured on the device — which quantized build to ship, attaches a signed manifest, and blocks anything that regresses past the budget.

## How it works under the hood

Both workflows are thin wrappers around the published [`TinyEdgeAI/tinyedge-agent`](https://github.com/TinyEdgeAI/tinyedge-agent) actions (`@v1`), which run two SDK commands you can also run locally (`pip install tinyedge`):

```
tinyedge optimize <model> --device jetson-orin-nano   # sweep the ladder on the device
tinyedge decide   <sweep-id> --profile max_quality    # pick the winner + sign the manifest
```

## Run it in your own repo

1. Fork this repo.
2. Add a repo **secret** `TINYEDGE_API_KEY` (get a key at [tinyedge.ai](https://tinyedge.ai)).
3. *(for the gate)* create a baseline and store its id as a repo **variable** `TINYEDGE_BASELINE`:
   ```bash
   tinyedge run "hf:bartowski/Llama-3.2-1B-Instruct-GGUF/Llama-3.2-1B-Instruct-Q4_K_M.gguf" \
     --device jetson-orin-nano --watch
   tinyedge baseline save <job-id> --name v1 && tinyedge baseline list
   ```
4. Push a change to `model.yaml`, or trigger **decide** from the Actions tab. A device must be online during the run.

## Verify the manifest

The deployment manifest is Ed25519-signed:
```bash
curl -s https://tinyedge.ai/api/manifest/public-key -o pub.pem
# verify the signature over the canonical JSON (signature + signatureAlg excluded)
```

---

<sub>Powered by [TinyEdge](https://tinyedge.ai) — benchmark, validate, and decide model deployments on real edge devices.</sub>
