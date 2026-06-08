"""Diagnostic: watch Teams audio sessions to design precise call start/end detection.

Read-only. Run it, then walk through these phases (watch the printout at each):
  (1) Teams open but NOT in a call   (~10 s)
  (2) join a call and TALK            (~15 s)
  (3) stay in the call but SILENT / everyone muted (~15 s)
  (4) END the call, keep watching     (~15 s)

The point: tell 'call ended' (session disappears / goes Expired) apart from a
'momentary silence' (session still present but Inactive). Paste the output back.
"""
import time

import pythoncom
from pycaw.pycaw import AudioUtilities

STATE = {0: "Inactive", 1: "Active", 2: "Expired"}
TEAMS = {"ms-teams.exe", "teams.exe"}

pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
print("watching Teams audio sessions every 1.5 s. Ctrl+C to stop.")
print("phases: (1) idle  (2) in call + talking  (3) in call + silent  (4) just ended")
print("-" * 60)
try:
    while True:
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception as e:  # noqa: BLE001
            print("GetAllSessions error:", e)
            time.sleep(1.5)
            continue

        rows = []
        for s in sessions:
            p = s.Process
            if p is None:
                continue
            try:
                name = p.name()
            except Exception:  # noqa: BLE001
                continue
            if name.lower() in TEAMS:
                try:
                    st = s.State
                except Exception:  # noqa: BLE001
                    st = -1
                rows.append(f"{name}(pid={p.pid}) state={STATE.get(st, st)}")

        stamp = time.strftime("%H:%M:%S")
        if rows:
            print(f"{stamp}  teams_sessions={len(rows)}  " + " | ".join(rows))
        else:
            print(f"{stamp}  teams_sessions=0  (no Teams audio session present)")
        time.sleep(1.5)
except KeyboardInterrupt:
    print("stopped")
finally:
    pythoncom.CoUninitialize()
