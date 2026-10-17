"""Reproducible regression run with the project's D-drive temporary evidence policy."""
import json
from pathlib import Path
import tempfile
import time
import unittest


if __name__=='__main__':
    scratch=Path('D:/CQWE_DATA/temp');scratch.mkdir(exist_ok=True)
    tempfile.tempdir=str(scratch)
    start=time.monotonic()
    with Path('D:/CQWE/local_v3_full_tests_d.log').open('w',encoding='utf-8') as out:
        class Result(unittest.TextTestResult):
            def addError(self,test,err):
                super().addError(test,err)
                out.write('\n'+self.errors[-1][1]);out.flush()
            def addFailure(self,test,err):
                super().addFailure(test,err)
                out.write('\n'+self.failures[-1][1]);out.flush()
        r=unittest.TextTestRunner(stream=out,verbosity=1,resultclass=Result).run(
            unittest.defaultTestLoader.discover('tests'))
    result={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
            'skipped':len(r.skipped),'elapsed_seconds':time.monotonic()-start,'success':r.wasSuccessful()}
    Path('reports/local_v3_test_results_20261015.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result));raise SystemExit(not r.wasSuccessful())
