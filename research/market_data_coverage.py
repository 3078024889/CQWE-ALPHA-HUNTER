"""Publish explicit coverage and gaps; a catalog row is not an integrated feed."""
import json
from pathlib import Path
from cqwe.local_autopilot import atomic


def main():
    data=json.loads(Path('reports/event_history_expanded_catalog_20261016.json').read_text(encoding='utf-8'))
    rows=[{'node':k,'calendar_entries':v,'status':'CALENDAR_AND_PRICE_WINDOWS',
           'consensus_point_in_time_complete':False,'initial_release_vintage_authenticated':False,
           'realtime_actual_values_connected':False} for k,v in data['counts'].items()]
    gaps=[
      ('CORE_CPI_PCE_PPI','Core, headline, monthly and yearly values need distinct units but shared event clusters','https://www.bls.gov/cpi/'),
      ('NFP_COMPONENTS','Wages, unemployment, participation and revisions share one employment release','https://www.bls.gov/news.release/empsit.toc.htm'),
      ('FED_MINUTES_SEP_PRESS_CONFERENCE','Separate timestamps; do not fold minutes or press conference into the rate-decision label','https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'),
      ('SPGLOBAL_FLASH_PMI','Need archived actual release timestamps and point-in-time data access','https://www.pmi.spglobal.com/Public/Release/ReleaseDates?language=en&os=v'),
      ('UMICH_SENTIMENT_INFLATION_EXPECTATIONS','Some free historical data embargoed four weeks; live availability not assumed','https://data.sca.isr.umich.edu/faq.php'),
      ('CONFERENCE_BOARD_CONFIDENCE','Need vintage actual values, release calendar and accessible consensus','https://www.conference-board.org/topics/consumer-confidence/'),
      ('EIA_OIL_INVENTORIES','Official release schedule identified; no adapter or matched sample set yet','https://www.eia.gov/petroleum/supply/weekly/schedule.php'),
      ('CFTC_POSITIONING','Publication date differs from position observation date','https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm'),
      ('FED_BALANCE_SHEET','Need actual availability dates and publication delay','https://www.federalreserve.gov/releases/h41/'),
      ('TREASURY_AUCTIONS_TGA_RRP','Separate announcements, auctions, settlements and reported balances; adapters incomplete',None),
      ('ETF_FLOWS_HOLDINGS','Issuer primary filings, shares and NAV; daily estimates are not intraday actual flows',None),
      ('REGULATION_POLITICS_TARIFFS_WAR','Official headlines partially observed; first-seen timestamps and fact confirmation needed',None),
      ('HACKS_CUSTODY_STABLECOINS','Protocol/exchange primary disclosures and on-chain timestamps; sources not complete',None),
      ('TOKEN_UNLOCKS_CHAIN_UPGRADES_CONFERENCES','Three conference opening dates only; no claim of complete agenda or token calendar',None),
      ('CROSS_ASSET_RATES_DOLLAR_OIL_EQUITIES','Need synchronized historical prices and publication-lag rules',None),
      ('DERIVATIVES_MICROSTRUCTURE','Orderbook, trades, OI, funding and sampled liquidations exist in separate live research; historical full orderbook missing',None),
    ]
    rows.extend({'node':key,'status':'PARTIAL_OR_NOT_CONNECTED','gap':gap,'primary_source':source}
                for key,gap,source in gaps)
    atomic(Path('reports/market_data_coverage_20261016.json'),
           {'nodes':rows,'calendar_types':len(data['counts']),'all_market_influences_complete':False,
            'unknown_cause_must_remain_unknown':True,'profitability_proven':False,'real_orders':0})
    print(json.dumps({'calendar_types':len(data['counts']),'explicit_gap_groups':len(gaps)}))


if __name__=='__main__':main()
