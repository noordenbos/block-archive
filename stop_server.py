"""Stop only the Spatial Prep server listening on 127.0.0.1:8774."""
import argparse
import os
import signal
import subprocess
import sys

PORT=8774

def listeners():
    try:
        out=subprocess.check_output(['lsof','-nP',f'-iTCP:{PORT}','-sTCP:LISTEN','-t'],text=True,stderr=subprocess.DEVNULL)
    except (FileNotFoundError,subprocess.CalledProcessError):
        return []
    return sorted({int(line) for line in out.splitlines() if line.strip().isdigit()})

parser=argparse.ArgumentParser(description='Stop the local Spatial Prep server.')
parser.add_argument('--yes',action='store_true',help='stop without prompting')
args=parser.parse_args()
pids=listeners()
if not pids:
    print(f'No process is listening on 127.0.0.1:{PORT}.')
    raise SystemExit(0)
print(f'Found listener(s) on 127.0.0.1:{PORT}: {", ".join(map(str,pids))}')
for pid in pids:
    try: print(subprocess.check_output(['ps','-p',str(pid),'-o','pid=,command='],text=True).strip())
    except Exception: pass
if not args.yes:
    answer=input('Stop this Spatial Prep server? Browser-saved project data is retained. Type yes: ').strip().lower()
    if answer!='yes': print('No process stopped.'); raise SystemExit(0)
for pid in pids:
    try: os.kill(pid,signal.SIGTERM); print(f'Sent stop signal to PID {pid}.')
    except ProcessLookupError: print(f'PID {pid} already stopped.')
