"""Single-request public calendar extraction. FRED displays Central Time."""
import json
import re
import time
from pathlib import Path
from research.history_sources import fetch,ROOT

RELEASES={194:'US_ADP',9:'US_RETAIL',53:'US_GDP',54:'US_PCE',180:'US_CLAIMS',
          10:'US_CPI',50:'US_NFP',46:'US_PPI',192:'US_JOLTS',
          13:'US_INDUSTRIAL_PRODUCTION',27:'US_RESIDENTIAL_CONSTRUCTION',
          97:'US_NEW_HOME_SALES',95:'US_M3_ORDERS'}


if __name__=='__main__':
    status=[]
    for rid in RELEASES:
        for year in (2024,2025,2026):
            status.append(fetch((f'fred_{rid}_{year}',f'https://fred.stlouisfed.org/releases/calendar?rid={rid}&y={year}')))
            time.sleep(.2)
    (ROOT/'fred_fetch_status.json').write_text(json.dumps(status,indent=2))
    print(json.dumps(status))
