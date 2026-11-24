"""Record the AP agent's answers to each business's three suggested prompts into seed/agent_cache.json (committed), so
they are instant on the live site. Needs GEMINI_API_KEY. Run from backend/:   python -m seed.export_agent_cache

It loads the full demo (every client business) into a temporary database, asks the real Gemini agent each prompt once, and
stores the tool calls it made plus its reply. At runtime app/agent.py replays the tool calls against the live invoices
(so proposals are always computed fresh) and reuses only the wording, and only while that business's invoices are in
exactly the recorded state. Recordings that are already in the file for the same state are kept (no Gemini call).
"Today" is fixed for each recording, because the demo invoices are dated early November: "due this week" is meaningful.
"""
import json
import tempfile
import time
from pathlib import Path

from app import agent, config, db, pipeline
from seed.data import DEMO_RUNS

RECORDED_TODAY = {1: "2026-11-06", 2: "2026-11-16"}
HERE = Path(__file__).parent


def main():
    from seed.seed import seed_db
    path = HERE / "agent_cache.json"
    have = json.loads(path.read_text()) if path.exists() else []
    entries = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config.DB_PATH = str(Path(tmp) / "agent.db")
        seed_db()
        conn = db.connect()
        for biz, inv in DEMO_RUNS:  # same order as the demo, so the invoice ids match the live demo
            pipeline.process_invoice(conn, (HERE / "invoices" / inv["file"]).read_bytes(), inv["file"], business_id=biz)
        for biz, prompts in agent.SUGGESTIONS.items():
            signature = agent.state_signature(conn, biz)
            for prompt in prompts:
                key = (biz, agent._norm(prompt), signature)
                old = next((e for e in have if (e.get("business_id", 1), e["prompt"], e["signature"]) == key), None)
                if old:
                    old.setdefault("business_id", biz)
                    entries.append(old)
                    print(f"kept: business {biz} {prompt!r}", flush=True)
                    continue
                for attempt in range(1, 5):  # Gemini can time out or be briefly overloaded
                    try:
                        entry = agent.record(conn, prompt, RECORDED_TODAY[biz], biz)
                        break
                    except Exception as e:
                        print(f"attempt {attempt} failed ({type(e).__name__}); retrying", flush=True)
                        time.sleep(8)
                else:
                    raise SystemExit(f"could not record {prompt!r}")
                print(f"recorded: business {biz} {prompt!r} -> {[s['tool'] for s in entry['steps']]}", flush=True)
                entries.append(entry)
                time.sleep(2)
        conn.close()
    path.write_text(json.dumps(entries, indent=1))
    print(f"saved {len(entries)} recordings")


if __name__ == "__main__":
    main()
