"""Finite event taxonomy; classification does not predetermine price direction."""

FAMILIES = {
    'US_CPI': ('headline/core', 'MoM/YoY', 'first-release', 'consensus'),
    'INFLATION_OTHER': ('PCE/PPI/wages', 'country', 'period', 'consensus'),
    'EMPLOYMENT_GROWTH': ('payrolls/unemployment/GDP/PMI/retail', 'revisions', 'consensus'),
    'MONETARY_POLICY': ('central-bank', 'rate/QE/QT/guidance', 'decision-vs-expectation'),
    'LIQUIDITY_FISCAL': ('repo/reserves/TGA/RRP/fiscal', 'announced-vs-effective', 'amount-unit'),
    'POLITICAL_STATEMENT': ('speaker', 'original-record', 'statement-vs-policy', 'authenticity'),
    'REGULATION_LEGAL': ('jurisdiction', 'proposal/approval/enforcement', 'effective-date'),
    'WAR_GEOPOLITICS': ('first-report', 'confirmation', 'escalation/ceasefire', 'location'),
    'SANCTIONS_TRADE': ('sanctions/tariffs/export-controls', 'scope', 'effective-date'),
    'ETF_FLOWS': ('fund', 'flow-date', 'publication-time', 'currency', 'net-vs-gross', 'revisions'),
    'ETF_DECISION': ('filing/approval/rejection/launch', 'issuer', 'underlying'),
    'HACK_EXPLOIT': ('chain', 'incident-time', 'disclosure-time', 'confirmed-loss', 'recovery'),
    'EXCHANGE_CUSTODY': ('venue', 'withdrawal-halt/insolvency/outage', 'exposure'),
    'STABLECOIN_CREDIT': ('issuer', 'peg/reserves/redemption', 'confirmed-exposure'),
    'CHAIN_TOKEN': ('chain/upgrade/unlock/outage', 'announcement-vs-execution', 'affected-assets'),
    'INSTITUTIONAL_FLOWS': ('treasury-purchase/sale/transfer', 'confirmed-owner', 'transfer-is-not-sale'),
    'OTHER_RELEVANT': ('original-source', 'economic-mechanism', 'affected-assets'),
}


def identity(event):
    if event.get('family') not in FAMILIES:
        raise ValueError('EVENT_FAMILY_NOT_REGISTERED')
    if not isinstance(event.get('event_id'),str) or not 1<=len(event['event_id'])<=200:
        raise ValueError('EVENT_ID_REQUIRED')
    cluster=event.get('cluster_id',event['event_id'])
    if not isinstance(cluster,str) or not 1<=len(cluster)<=200:
        raise ValueError('EVENT_CLUSTER_REQUIRED')
    return cluster
