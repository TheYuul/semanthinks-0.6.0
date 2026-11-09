"""
simulate.py - run a fixed set of titles through the running backend and report decisions and speed.

  1. start the backend:   cd backend && uvicorn classify_service:app --port 8000
  2. run:                 python tools/simulate.py [--subjects algorithms-and-complexity ...] [--context "..."] [--url http://127.0.0.1:8000]

Titles are written by hand for this check (they are not from the training data). 'expect' says what a student of
Computer Science / Information Technology should see: keep = relevant, hide = distracting. Use it to rehearse the demo
and to see which topics the model is unsure about. Pass --thumbs to also send a ytimg thumbnail id when listed.
"""
import argparse, json, statistics, sys, time, urllib.request

CASES = [
    ("keep", "Binary Search Trees Explained | Data Structures and Algorithms"),
    ("keep", "Introduction to SQL Joins | Database Systems Lecture 5"),
    ("keep", "Big-O Notation and Time Complexity for Beginners"),
    ("keep", "Python Programming Full Course for Beginners"),
    ("keep", "How TCP/IP Works | Computer Networks"),
    ("keep", "Deterministic Finite Automata (DFA) Examples | Theory of Computation"),
    ("keep", "Machine Learning Basics: Linear Regression from Scratch"),
    ("keep", "Operating Systems: Process Scheduling Algorithms"),
    ("keep", "Git and GitHub Crash Course for Students"),
    ("keep", "Cybersecurity Fundamentals: Encryption and Hashing"),
    ("hide", "I Tried the Spiciest Noodles in the World (Mukbang)"),
    ("hide", "Celebrity Gossip: Who Is Dating Who This Week"),
    ("hide", "Minecraft Hardcore Survival Let's Play Ep. 52"),
    ("hide", "Top 10 Funniest Pranks of the Year"),
    ("hide", "Official Movie Trailer | Summer Blockbuster 2026"),
    ("hide", "Pinoy Teleserye Best Moments Compilation"),
    ("hide", "Easy 5-Minute Chocolate Cake Recipe"),
    ("hide", "NBA Highlights: Lakers vs Warriors Full Game"),
    ("hide", "K-Pop Dance Challenge Goes Viral"),
    ("hide", "Subscribe to Shopee VIP+ today and enjoy Free Netflix subscription"),
]


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()), (time.time() - t) * 1000


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--context", default="Computer Science and Information Technology: programming, algorithms, data structures, databases, networks, software engineering")
    ap.add_argument("--subjects", nargs="*", default=[]); ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    try:
        health = json.loads(urllib.request.urlopen(a.url + "/health", timeout=5).read())
    except Exception as e:
        sys.exit(f"backend not reachable at {a.url} ({e})")
    print("engine:", health.get("engine"), "| context:", a.context[:70], "\n")
    rows, times = [], []
    for expect, title in CASES:
        for _ in range(a.repeat):
            res, ms = post(a.url + "/api/classify", {"text": title, "context": a.context, "subjects": a.subjects})
            times.append(ms)
        ok = (res["action"] == "hide") == (expect == "hide") if res["action"] != "warn" else None
        rows.append((expect, res["action"], ok))
        print(f"{'ok ' if ok else ('?  ' if ok is None else 'BAD')} expect={expect:4s} got={res['action']:5s} C={res['score']:.2f} p={res['p_distract']:.2f} {ms:6.0f} ms | {title[:62]}")
    decided = [r for r in rows if r[2] is not None]
    keep = [r for r in rows if r[0] == "keep"]; hide = [r for r in rows if r[0] == "hide"]
    print(f"\ncorrect on decided items: {sum(r[2] for r in decided)}/{len(decided)}  | warned (unsure): {sum(r[2] is None for r in rows)}")
    print(f"relevant wrongly hidden: {sum(r[1]=='hide' for r in keep)}/{len(keep)}  | distracting kept (allow): {sum(r[1]=='allow' for r in hide)}/{len(hide)}")
    print(f"latency: median {statistics.median(times):.0f} ms, p90 {sorted(times)[int(len(times)*0.9)-1]:.0f} ms (first call includes warm-up)")


if __name__ == "__main__":
    main()
