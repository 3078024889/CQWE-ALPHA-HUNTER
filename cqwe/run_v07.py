"""CQWE V07 one-shot CLI. No exchange keys or order placement."""
import argparse
import json
from .microstructure import study

def main():
    p=argparse.ArgumentParser(description='CQWE V07 offline microstructure research (NO ORDERS)')
    p.add_argument('--input',required=True)
    p.add_argument('--oi',default=None)
    p.add_argument('--out',default='reports/v07_microstructure.json')
    a=p.parse_args()
    report=study(a.input,a.oi,a.out)
    print(json.dumps(report,indent=2,ensure_ascii=False))
    print('CQWE_V07_OFFLINE_RESEARCH_PASS | NO ORDERS')

if __name__=='__main__':main()
