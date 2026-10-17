"""Build a narrowly allowlisted, checksum-indexed local research bundle."""
import hashlib
import json
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    output = root.parent / 'output'
    output.mkdir(exist_ok=True)
    destination = output / 'CQWE_V81_V85_RESEARCH.zip'
    names = [
        'cqwe/__init__.py', 'cqwe/copernican_experiment_v81_v85.py',
        'cqwe/tidal_hunter_v66_v70.py', 'cqwe/dendrite_evolution_v55.py',
        'cqwe/tidal_hunter_v71_v75.py', 'cqwe/tidal_hunter_v76_v80.py',
        'cqwe/copernican_lab_v33.py', 'tests/test_v81_v85.py',
        'research/run_v85_public.py', 'RUN_RESEARCH_V85.ps1',
        'audit-context/DOSSIER.md', 'reports/CQWE_REVIEW_20261015.md',
        'reports/v85_book_index.json', 'reports/v85_copernican_historical_20261015.json',
    ]
    names += [p.relative_to(root).as_posix() for p in
              sorted((root/'reports/v85_public_20261015').glob('*.json'))]
    payload = {name: (root/name).read_bytes() for name in names}
    payload['tests/__init__.py'] = b''
    payload['research/__init__.py'] = b''
    payload['validation/full_repository_tests.log'] = (root.parent/'validation_tests.log').read_bytes()
    payload['README_zh.md'] = (
        '# CQWE V81-V85\n\n'
        '研究交付；未证明盈利，未下单。完整中文结论见 reports/CQWE_REVIEW_20261015.md。\n\n'
        '需 Python 3.10+；无第三方运行依赖。解压后在本目录运行：\n\n'
        '```powershell\n'
        "powershell -NoProfile -File .\\RUN_RESEARCH_V85.ps1 -Python 'C:\\Python314\\python.exe'\n"
        '```\n\n'
        '启动器只运行10项新测试并离线复算两个BTC历史批次，不安装定时任务。\n'
        '591项全仓测试结果属于原始完整项目；本包只携带必要研究模块和10项新增测试。\n'
        'SOURCE_MANIFEST.json记录包内各文件SHA256；这不认证交易所或盈利。\n'
        '每次输出写入新目录；要继续学习，需提供完全更新且不重叠的行情，并传入--previous报告路径。\n'
    ).encode('utf-8')
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            archive.writestr(name, data)
        archive.writestr('SOURCE_MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP_CRC_ERROR')
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError('ZIP_HASH_ERROR')
        verify_dir = output/'v85_bundle_verify'
        verify_dir.mkdir(exist_ok=False)
        archive.extractall(verify_dir)
    print(json.dumps({'zip': str(destination), 'files': len(payload)+1,
                      'bytes': destination.stat().st_size,
                      'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
