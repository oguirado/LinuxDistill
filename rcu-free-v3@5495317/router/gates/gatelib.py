"""gatelib.py - shared leg runner for the lx router gates. A gate module defines positive() and must_fail();
each returns (ok: bool, detail: str). `python3 -I -B gate_x.py positive|must_fail` exits 0 on PASS, 1 on FAIL, 2 on ERROR."""
import os, sys
sys.dont_write_bytecode = True
GATES = os.path.dirname(os.path.abspath(__file__))
X = os.path.dirname(GATES)
sys.path.insert(0, os.path.join(X, "tools"))
import lxlib  # noqa: E402,F401


def main(positive, must_fail):
    leg = sys.argv[1] if len(sys.argv) > 1 else "positive"
    try:
        ok, detail = (positive if leg == "positive" else must_fail)()
    except Exception as e:  # a crash is ERROR (rc 2): never a PASS, and never counted as an expected must-FAIL
        print(f"{leg}: ERROR - {type(e).__name__}: {str(e)[:300]}")
        sys.exit(2)
    print(f"{leg}: {'PASS' if ok else 'FAIL'} - {detail}")
    sys.exit(0 if ok else 1)
