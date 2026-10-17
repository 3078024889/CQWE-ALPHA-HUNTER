"""Save public source evidence without importing or executing downloaded code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "reports" / "polymarket_sources_20261015"
SOURCES = {
    "poly_maker_readme": "https://raw.githubusercontent.com/warproxxx/poly-maker/main/README.md",
    "poly_maker_tips": "https://raw.githubusercontent.com/warproxxx/poly-maker/main/TIPS.md",
    "poly_maker_quoting": "https://raw.githubusercontent.com/warproxxx/poly-maker/main/src/polymaker/strategy/quoting.py",
    "poly_maker_license": "https://raw.githubusercontent.com/warproxxx/poly-maker/main/LICENSE",
    "poly_data_readme": "https://raw.githubusercontent.com/warproxxx/poly_data/main/README.md",
    "poly_data_license": "https://raw.githubusercontent.com/warproxxx/poly_data/main/LICENSE",
    "synpath_readme": "https://raw.githubusercontent.com/Synpath-ai/prediction-market-arbitrage-trading-bot/main/README.md",
    "synpath_pricing": "https://raw.githubusercontent.com/Synpath-ai/prediction-market-arbitrage-trading-bot/main/src/arbitrage.py",
    "synpath_paper_bot": "https://raw.githubusercontent.com/Synpath-ai/prediction-market-arbitrage-trading-bot/main/trading/bot.py",
    "synpath_license": "https://raw.githubusercontent.com/Synpath-ai/prediction-market-arbitrage-trading-bot/main/LICENSE",
    "realfish_readme": "https://raw.githubusercontent.com/realfishsam/prediction-market-arbitrage-bot/main/README.md",
    "realfish_bot": "https://raw.githubusercontent.com/realfishsam/prediction-market-arbitrage-bot/main/src/bot.js",
    "realfish_pricing": "https://raw.githubusercontent.com/realfishsam/prediction-market-arbitrage-bot/main/src/arbitrage.js",
    "realfish_license": "https://raw.githubusercontent.com/realfishsam/prediction-market-arbitrage-bot/main/LICENSE",
    "konis_readme": "https://raw.githubusercontent.com/the-konis/polymarket-opensource-trading-bot/main/README.md",
    "konis_license": "https://raw.githubusercontent.com/the-konis/polymarket-opensource-trading-bot/main/LICENSE",
    "emmanuel_readme": "https://raw.githubusercontent.com/emmanuelwestra/Polymarket-Trading-Bot/main/README.md",
    "emmanuel_license": "https://raw.githubusercontent.com/emmanuelwestra/Polymarket-Trading-Bot/main/LICENSE",
}


def fetch(item):
    name, url = item
    result = {"name": name, "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url, headers={"User-Agent": "CQWE-research/1.0"}), timeout=25) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("source exceeds snapshot limit")
            path = ROOT / (name + ".txt")
            path.write_bytes(body)
            result.update(status="SAVED", path=str(path), bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    except Exception as exc:
        result.update(status="UNAVAILABLE", error=str(exc))
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(fetch, SOURCES.items()))
    manifest = {"mode": "READ_ONLY_SOURCE_SNAPSHOT", "third_party_code_executed": False,
                "commit_pinned": False, "limitation": "Branch URLs may change; hashes identify retrieved file bytes only.",
                "sources": sources}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved": sum(s["status"] == "SAVED" for s in sources),
                      "unavailable": [s["name"] for s in sources if s["status"] != "SAVED"],
                      "manifest": str(ROOT / "manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
