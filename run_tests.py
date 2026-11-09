"""
run_tests.py - one command that runs every Semanthinks test and says clearly what passed, failed or was skipped.

    python run_tests.py              # run everything that can run on this machine
    python run_tests.py --strict     # a skipped test (missing package, no Node) counts as a failure
    python run_tests.py --only pipeline popup      # only tests whose name contains one of these words

One-time setup:
    pip install -r requirements-dev.txt
    npm install            # installs Playwright for the browser tests (needs Node.js)
    npx playwright install chromium

Exit code: 0 = nothing failed (and, with --strict, nothing skipped), 1 = a test failed or --strict found a skip.
"""
import argparse, importlib.util, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = [
    ("Dense head and decision rule", "tests/test_fusion_head.py", ["numpy"]),
    ("Training pipeline, bundle, engine", "tests/test_pipeline.py", ["numpy", "sklearn"]),
    ("Dataset tools", "tests/test_dataset_tools.py", ["numpy", "pandas", "openpyxl", "sklearn"]),
    ("Labeling tools and JS/Python parity", "tests/test_labeling_tools.py", ["numpy", "pandas", "openpyxl"]),
    ("Image simulator", "tests/test_image_simulator.py", ["numpy", "PIL"]),
]
NODE = [
    ("Subject catalog (Node)", "tests/catalog.test.js", False),
    ("URL and link-intent rules (Node)", "tests/url_tools.test.js", False),
    ("Popup in a browser", "tests/popup.e2e.js", True),
    ("Content script in a browser", "tests/content.e2e.js", True),
]
PIP = {"sklearn": "scikit-learn", "PIL": "pillow"}


def have(mod):
    return importlib.util.find_spec(mod) is not None


def node_env():
    env = dict(os.environ, PYTHONUTF8="1")
    extra = []
    if shutil.which("npm"):
        try:
            g = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=30, shell=(os.name == "nt")).stdout.strip()
            if g: extra.append(g)
        except Exception:
            pass
    extra.append(str(ROOT / "node_modules"))
    env["NODE_PATH"] = os.pathsep.join(extra + ([env["NODE_PATH"]] if env.get("NODE_PATH") else []))
    return env


def playwright_ok(env):
    if not shutil.which("node"): return False
    r = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode == 0


def run(cmd, env):
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT, timeout=900, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip(), time.time() - t


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--strict", action="store_true"); ap.add_argument("--only", nargs="*", default=[])
    a = ap.parse_args()
    want = lambda name, path: not a.only or any(w.lower() in (name + path).lower() for w in a.only)
    env = node_env(); results = []

    for name, path, mods in PY:
        if not want(name, path): continue
        missing = [m for m in mods if not have(m)]
        if missing:
            results.append((name, "SKIP", f"missing {', '.join(PIP.get(m, m) for m in missing)}: pip install -r requirements-dev.txt", 0)); continue
        code, out, dt = run([sys.executable, path], env)
        results.append((name, "PASS" if code == 0 else "FAIL", "" if code == 0 else "\n".join(out.splitlines()[-12:]), dt))

    pw = None
    for name, path, needs_browser in NODE:
        if not want(name, path): continue
        if not shutil.which("node"):
            results.append((name, "SKIP", "Node.js not found (install from nodejs.org)", 0)); continue
        if needs_browser:
            if pw is None: pw = playwright_ok(env)
            if not pw:
                results.append((name, "SKIP", "Playwright not found: run `npm install` and `npx playwright install chromium`", 0)); continue
        code, out, dt = run(["node", path], env)
        results.append((name, "PASS" if code == 0 else "FAIL", "" if code == 0 else "\n".join(out.splitlines()[-12:]), dt))

    print()
    w = max(len(r[0]) for r in results) if results else 10
    for name, st, note, dt in results:
        print(f"  {st:4s}  {name:<{w}}  {f'{dt:5.1f}s' if dt else '     -'}" + (f"   {note.splitlines()[0]}" if st == "SKIP" else ""))
    for name, st, note, _ in results:
        if st == "FAIL": print(f"\n--- {name} (last lines of output) ---\n{note}")
    fails = [r for r in results if r[1] == "FAIL"]; skips = [r for r in results if r[1] == "SKIP"]
    print(f"\n{len(results) - len(fails) - len(skips)} passed, {len(fails)} failed, {len(skips)} skipped.")
    if skips and not fails: print("Skipped tests did not run. Install what they name, or use --strict to treat skips as failures.")
    sys.exit(1 if fails or (a.strict and skips) else 0)


if __name__ == "__main__":
    main()
