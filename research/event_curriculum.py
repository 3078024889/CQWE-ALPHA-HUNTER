"""Reproduce the bounded, cached October 2026 event-research batch sequentially."""
import os
from pathlib import Path
import subprocess
import sys


if __name__=='__main__':
    if os.name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
    repo=Path(__file__).resolve().parents[1]
    modules=('research.build_event_history','research.event_history_impact','research.learn_event_history',
             'research.spike_casebook','research.extract_release_values','research.publish_event_history',
             'research.make_macro_watch_plan')
    for module in modules:
        subprocess.run([sys.executable,'-u','-X','utf8','-m',module],cwd=repo,check=True,
            creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0)
