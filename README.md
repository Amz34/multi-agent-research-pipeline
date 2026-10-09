# Multi-Agent Research Pipeline — crashproof, hand-wired, zero framework

[![ci](https://github.com/Amz34/multi-agent-research-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Amz34/multi-agent-research-pipeline/actions/workflows/ci.yml)

![Four-stage research pipeline: researcher, summarizer, evaluator, coordinator](assets/pipeline-overview.jpg)

> **Warning: agents don't behave.**
>
> Every tutorial shows you the happy path — three agents, one prompt, flawless output.
> Nobody shows you the second run. That's where it all falls apart.
>
> This is the pipeline I run in production. Four agents, wired by hand.
> No framework. No hidden retries. Every failure stays visible.

## What this is

A research pipeline that takes any topic and returns a **grounded, structured briefing**:

```json
{
  "title": "Impact of AI Agents on Developer Workflows",
  "keyPoints": ["...", "...", "..."],
  "takeaway": "...",
  "iterations": 1,
  "verdict": "APPROVED"
}
```

One command. Typically 10-15 seconds end to end (measured 11.3 s for a live run on a
2-vCPU cloud VM). No LangChain, no CrewAI, no orchestration dependencies — just an HTTP
client, a search library, and a strict quality gate.

## The four agents

```
topic ──▶ [researcher] ──▶ raw notes (with sources)
              │
notes ──▶ [summarizer] ──▶ structured JSON {title, keyPoints[3], takeaway}
              │
notes + summary ──▶ [evaluator] ──▶ "APPROVED" or "REVISE"
              │
[coordinator] runs the chain, checks every handoff,
              retries weak output (max 5 iterations), returns the best result
```

| Agent | Job | Failure mode if removed |
|---|---|---|
| **researcher** | Real web search → raw notes. No summary, no conclusions. | You summarize your own bias. |
| **summarizer** | Notes → strict JSON. 3 key points, one takeaway. | Unstructured prose nobody can use. |
| **evaluator** | Reads notes AND summary. Grounded? **APPROVED / REVISE**. | Polished wrong answers ship silently. |
| **coordinator** | Wires the three, owns the retry loop, caps at 5. | One weak pass and you're done. |

## Why no framework?

Because frameworks hide retries. A pipeline that *looks* like it worked is worse
than one that crashes — it hands you a **polished wrong answer** and nobody logged why.

Hand-wired agents fail loudly. You want loud. Logs are cheap; silent confidence isn't.

## The five crashproof rules

1. **Logging first.** Every agent call *and every handoff* is logged to a per-run JSONL
   file. Failures hide in handoffs, not in the agents — so we log the handoffs.
2. **Retry with backoff.** 429 / 5xx / network blips → exponential backoff + jitter.
3. **Hard timeouts.** One stuck upstream call can never hang the pipeline.
4. **Validate everything.** Empty topic → clean 400, not a stack trace.
5. **Cap the loop.** The evaluator can say REVISE forever; we cap at 5 and ship the best.

## Quickstart

```bash
git clone https://github.com/Amz34/multi-agent-research-pipeline.git
cd multi-agent-research-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your DEEPSEEK_API_KEY (any OpenAI-compatible endpoint works)
python cli.py "impact of AI agents on developer workflows"
```

Machine-readable? Logs go to stderr, the result is pure JSON on stdout:

```bash
python cli.py "your topic" > briefing.json
```

Makefile shortcuts: `make run TOPIC="your topic"`, `make test`, `make check`,
`make deploy` (install the systemd service), `make preview` (render the unit,
change nothing).

## Run it as a service

Crashproof also means *it comes back*:

```bash
sudo bash deploy.sh
# systemd unit: Restart=always, starts on boot, memory-capped

curl -X POST localhost:8088/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "Saudi Arabia facilities management market"}'
curl localhost:8088/health   # {"status":"ok"}
```

We killed the live service with `kill -9` while verifying this release: systemd
restarted it and `/health` answered **3.7 seconds** later (measured on a 2-vCPU VM).
That is the standard we hold every AI system we build to.

![CI and crash-recovery checks wired into the repository](assets/ci-cd-hardening.jpg)

Preview the unit before installing it — `deploy.sh --dry-run` prints the rendered
file and changes nothing:

```bash
bash deploy.sh --dry-run
```

## Verify it yourself

The test suite needs no network and no API key, so CI proves the guarantees above on
every push (Python 3.11 and 3.12) instead of asking you to trust the README:

```bash
make test      # 39 offline tests
make check     # compile every source file, then run the tests
```

What the suite actually asserts:

- the JSON extractor survives fenced blocks, prose wrappers and unparseable output,
  and raises a typed error when there is nothing to parse;
- a search failure degrades to an empty result set instead of raising;
- the LLM retry rail backs off and gives up after the configured attempts, and a
  permanent 4xx response is never retried;
- `run_pipeline_safe()` returns a structured error and **never** raises, so one bad
  topic cannot take the server down;
- the evaluator loop is capped: a verdict that never flips stops at `MAX_ITERATIONS`;
- the HTTP contract: `/health`, a 400 for a missing or over-long topic, and a 500
  carrying a JSON error body (no stack trace) when the pipeline fails;
- the deployment artifacts themselves: the unit carries `Restart=always` and a
  memory cap, and `deploy.sh` renders a valid unit.

## Known limitations

- The bundled server is Flask's development server (it prints a warning on start).
  Put it behind `waitress` or `gunicorn` before exposing it beyond localhost.
- Search is DuckDuckGo-backed, so grounding is only as good as DDG's index; the
  evaluator judges what the researcher retrieved, it does not fact-check sources.
- The evaluator is another LLM call, not an independent verifier.

## Go break it

The happy path takes 20 minutes to build. Breaking it properly is the real work.

- Feed it a vague topic (`"everything about AI"`) — still returns clean JSON.
- Empty topic — clean 400, logged.
- No API key — one clear error message, not a mystery.
- Kill the service mid-request — systemd restarts it; the next request works.

## What you can swap

- **Model**: any OpenAI-compatible API (`DEEPSEEK_URL`, `DEEPSEEK_MODEL`).
- **Search**: `agents/search.py` uses DuckDuckGo (no key required) — swap in
  Tavily/Brave/SerpAPI behind the same `research_notes()` signature.
- **Language**: the agents are 30 lines each. Port them to whatever you like.

## Say something

Star it if you'd run it. Open an issue when it breaks — the second run is where
the real lessons live, and that's the whole point of this repo.

What's the most polished wrong answer an AI ever gave you? Tell us. Issues are open.

## License

MIT. Steal it, break it, ship it — and tell us what broke.

---

Part of [my always-on agent stack](https://github.com/Amz34) · [Awesome Agent Infrastructure](https://github.com/Amz34/awesome-agent-infrastructure) (135 live-checked building blocks).
