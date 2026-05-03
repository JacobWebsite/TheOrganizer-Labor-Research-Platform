"""
Mergent Intellect Download Helper
==================================
Generates shuffled download ranges for Mergent Intellect bulk downloads.
Copies each range to clipboard one at a time. Press Enter to advance.

Mergent search uses two fields (start, end) to define a range of companies
sorted by revenue. Each range is 2,000 companies.

Usage:
  py scripts/etl/mergent_download_helper.py                    # start from beginning
  py scripts/etl/mergent_download_helper.py --status           # show progress
  py scripts/etl/mergent_download_helper.py --resume           # resume where you left off
  py scripts/etl/mergent_download_helper.py --reset            # start over

State is saved to mergent_download_state.json between sessions.
"""

import argparse
import json
import os
import random
import sys

try:
    import pyperclip
except ImportError:
    print("Installing pyperclip...")
    os.system(sys.executable + " -m pip install pyperclip --quiet")
    import pyperclip

TOTAL_COMPANIES = 1768389
PAGE_SIZE = 2000
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mergent_download_state.json")


def generate_all_ranges():
    """Generate all (start, end) ranges."""
    ranges = []
    for i in range(0, TOTAL_COMPANIES, PAGE_SIZE):
        start = i + 1
        end = min(i + PAGE_SIZE, TOTAL_COMPANIES)
        ranges.append((start, end))
    return ranges


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return None


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def init_state(seed=42):
    """Create a new shuffled download plan."""
    ranges = generate_all_ranges()
    random.seed(seed)
    random.shuffle(ranges)
    state = {
        "total_ranges": len(ranges),
        "completed": [],
        "skipped": [],
        "queue": ranges,
        "seed": seed,
    }
    save_state(state)
    return state


def show_status(state):
    total = state["total_ranges"]
    done = len(state["completed"])
    skipped = len(state["skipped"])
    remaining = len(state["queue"])
    companies_done = done * PAGE_SIZE
    companies_remaining = remaining * PAGE_SIZE

    print("=" * 50)
    print("MERGENT DOWNLOAD PROGRESS")
    print("=" * 50)
    print("Total ranges:     %d" % total)
    print("Completed:        %d  (~%s companies)" % (done, "{:,}".format(companies_done)))
    print("Skipped:          %d" % skipped)
    print("Remaining:        %d  (~%s companies)" % (remaining, "{:,}".format(companies_remaining)))
    print("Progress:         %.1f%%" % (100.0 * done / total if total else 0))
    print()

    if state["queue"]:
        nxt = state["queue"][0]
        print("Next range:       %d - %d" % (nxt[0], nxt[1]))

    if state["completed"]:
        last = state["completed"][-1]
        print("Last completed:   %d - %d" % (last[0], last[1]))


def run_interactive(state):
    """Interactive download session. One number at a time, any key to advance."""
    import msvcrt

    print("=" * 50)
    print("MERGENT DOWNLOAD HELPER")
    print("=" * 50)
    print()
    print("Flow: START copied -> you paste -> press any key ->")
    print("      END copied -> you paste -> press any key ->")
    print("      (download the file) -> press any key -> next range")
    print()
    print("  s = skip    b = go back    q = quit")
    print()

    done_count = len(state["completed"])
    session_count = 0
    CAPTCHA_INTERVAL = 20

    def wait_key():
        """Wait for a single keypress, return the character."""
        b = msvcrt.getch()
        if b in (b"\x03", b"\x1b"):  # Ctrl+C or Escape
            raise KeyboardInterrupt
        return b.decode("utf-8", errors="ignore").lower()

    while state["queue"]:
        current = state["queue"][0]
        start, end = current
        remaining = len(state["queue"])
        total = state["total_ranges"]

        print("-" * 50)
        print("  Range %d of %d  |  %d remaining  |  %.1f%% done" % (
            done_count + 1, total, remaining, 100.0 * done_count / total
        ))
        print()

        # Step 1: Copy START
        pyperclip.copy(str(start))
        print("  START: %d  [ON CLIPBOARD - paste into first field]" % start)

        try:
            key = wait_key()
        except KeyboardInterrupt:
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return

        if key == "q":
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return
        if key == "s":
            state["queue"].pop(0)
            state["skipped"].append(list(current))
            save_state(state)
            print("  >> Skipped.\n")
            continue
        if key == "b":
            if state["completed"]:
                last = state["completed"].pop()
                state["queue"].insert(0, last)
                done_count -= 1
                save_state(state)
                print("  >> Back to %d-%d\n" % (last[0], last[1]))
            else:
                print("  >> Nothing to undo.\n")
            continue

        # Step 2: Copy END
        pyperclip.copy(str(end))
        print("  END:   %d  [ON CLIPBOARD - paste into second field]" % end)

        try:
            key = wait_key()
        except KeyboardInterrupt:
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return

        if key == "q":
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return

        # Step 3: Mark done, wait for download confirmation
        print("  >> Download the file, then press any key for next range")

        try:
            key = wait_key()
        except KeyboardInterrupt:
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return

        if key == "q":
            save_state(state)
            print("\nSaved. Use --resume to continue.")
            return

        state["queue"].pop(0)
        state["completed"].append(list(current))
        done_count += 1
        session_count += 1
        save_state(state)
        print("  >> Done. (%d completed, %d this session)\n" % (done_count, session_count))

        if session_count % CAPTCHA_INTERVAL == 0:
            print("  !! CAPTCHA likely incoming (%d downloads this session)" % session_count)
            print("  !! Solve it in the browser, then press any key to continue")
            print()
            try:
                wait_key()
            except KeyboardInterrupt:
                save_state(state)
                print("\nSaved. Use --resume to continue.")
                return

    print("\nAll ranges completed!")
    show_status(state)


def run_auto(state, count, delay):
    """Auto-copy mode: cycles clipboard through START/END pairs on a timer.

    Just keep pasting into Mergent. The clipboard changes every few seconds.
    Beeps between START and END so you know which field you're on.
    """
    import time
    import winsound

    total = min(count, len(state["queue"]))
    done_count = len(state["completed"])

    print("=" * 50)
    print("AUTO-COPY MODE")
    print("=" * 50)
    print()
    print("  Ranges to cycle: %d" % total)
    print("  Delay: %.1f seconds between copies" % delay)
    print()
    print("  LOW beep  = START number on clipboard")
    print("  HIGH beep = END number on clipboard")
    print()
    print("  Just keep pasting into Mergent.")
    print("  Press Ctrl+C to stop early (progress saved).")
    print()
    print("  Starting in 3 seconds...")
    time.sleep(3)

    session_count = 0
    try:
        for i in range(total):
            if not state["queue"]:
                break

            current = state["queue"][0]
            start, end = current
            session_count += 1

            # Copy START
            pyperclip.copy(str(start))
            try:
                winsound.Beep(440, 200)  # low beep = START
            except Exception:
                pass
            print("[%3d/%d]  START: %-8d  (paste now)" % (session_count, total, start), end="", flush=True)
            time.sleep(delay)

            # Copy END
            pyperclip.copy(str(end))
            try:
                winsound.Beep(880, 200)  # high beep = END
            except Exception:
                pass
            print("  ->  END: %-8d  (paste now)" % end, flush=True)
            time.sleep(delay)

            # Mark done
            state["queue"].pop(0)
            state["completed"].append(list(current))
            done_count += 1
            save_state(state)

            if session_count % 20 == 0:
                print()
                print("  !! %d downloads done — CAPTCHA likely. Pausing 30 seconds." % session_count)
                print("  !! Solve CAPTCHA, then pasting resumes automatically.")
                print()
                time.sleep(30)

    except KeyboardInterrupt:
        print("\n\nStopped. Progress saved.")

    print()
    print("Auto-copied %d ranges. %d total completed." % (session_count, done_count))
    show_status(state)


def main():
    parser = argparse.ArgumentParser(description="Mergent Download Helper")
    parser.add_argument("--status", action="store_true", help="Show progress")
    parser.add_argument("--resume", action="store_true", help="Resume previous session")
    parser.add_argument("--reset", action="store_true", help="Start over with new shuffle")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for shuffle")
    parser.add_argument("--export-csv", action="store_true", help="Export remaining ranges to CSV")
    parser.add_argument("--auto", type=int, metavar="N", help="Auto-copy mode: cycle N ranges with timed clipboard")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between clipboard copies in auto mode (default: 3)")
    args = parser.parse_args()

    state = load_state()

    if args.reset or state is None:
        if state and not args.reset:
            print("No saved state found. Initializing...")
        state = init_state(args.seed)
        print("Initialized %d ranges (shuffled with seed=%d)" % (state["total_ranges"], args.seed))
        if not args.status:
            print()

    if args.status:
        show_status(state)
        return

    if args.export_csv:
        outpath = os.path.join(os.path.dirname(STATE_FILE), "mergent_remaining_ranges.csv")
        with open(outpath, "w") as f:
            f.write("start,end\n")
            for s, e in state["queue"]:
                f.write("%d,%d\n" % (s, e))
        print("Exported %d remaining ranges to %s" % (len(state["queue"]), outpath))
        return

    if args.auto:
        run_auto(state, args.auto, args.delay)
        return

    run_interactive(state)


if __name__ == "__main__":
    main()
