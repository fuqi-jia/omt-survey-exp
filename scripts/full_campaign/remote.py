#!/usr/bin/env python3
"""Run a supplied Python file on the existing ExperimentOS control host.

WSL uses the already configured Windows SSH identity (lab VPN relay). No
credentials are read or logged. File transfer uses scp -O: SFTP is extremely
slow through this workstation's VPN. Example: remote.py probe.py.
"""
import argparse,base64,gzip,shutil,subprocess,sys
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('script',type=Path);args=ap.parse_args()
payload=base64.b64encode(gzip.compress(args.script.read_bytes())).decode()
command=f'echo {payload} | base64 -d | gzip -d | python3'
ps=shutil.which('powershell.exe') or '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
if Path(ps).exists():
 command="& ssh -o BatchMode=yes -o ConnectTimeout=15 jiafq@192.168.20.110 '"+command.replace("'","''")+"'"
 argv=[ps,'-NoProfile','-NonInteractive','-Command',command]
else:
 argv=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','jiafq@192.168.20.110',command]
raise SystemExit(subprocess.run(argv).returncode)
