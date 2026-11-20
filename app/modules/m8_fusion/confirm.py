"""融合确认后的缺口/采购重算。纯函数：输入批次payload，输出确认视图，不触碰数据库。"""
from decimal import Decimal

from app.domain import subtract, TARGET, length, merge
from app.numeric import number
from app.modules.m6_purchase.rules import apply as purchase_apply


def derive_confirmed(payload):
    proposal = payload['fusion_proposal']
    usable_by = {r['canonical']: r for r in payload['usable']}
    fused_usable = []
    for scene in proposal['fused_scenes']:
        canonical = scene['canonical']
        if canonical not in usable_by:
            continue
        base = dict(usable_by[canonical])
        base['clear'] = [(number(a), number(z)) for a, z in scene['fused_clear']]
        fused_usable.append(base)

    fused_coverage = merge([(number(a), number(z)) for a, z in proposal['fused_coverage']])
    gaps = subtract(TARGET, fused_coverage)

    pctx = {'usable': fused_usable}
    p6 = purchase_apply(pctx)
    selected = pctx['selected']
    cost = pctx['purchase_cost']
    covered = pctx['purchase_coverage']

    # 每个被采购场景的来源观测证据（段级溯源）
    provenance = {}
    for seg in proposal['segments']:
        provenance.setdefault(seg['融合场景'], []).append({
            '来源场景': seg['来源场景'], '来源行号': seg['来源行号'],
            '来源版本': seg['来源版本'], '采集时间': seg['采集时间'],
            '段宽度_度': seg['段宽度_度'], '来源角色': seg['来源角色'],
        })

    ledger = []
    for r in selected:
        ledger.append({
            '场景': r['canonical'],
            '价格_CNY': str(r['price_n']),
            '新增覆盖_度': str(r['gain']),
            '来源观测': provenance.get(r['canonical'], []),
        })

    gap_rows = [{'缺口起点': str(a), '缺口终点': str(z), '缺口宽度_度': str(z - a)} for a, z in gaps]
    purchase_rows = [
        {'场景': r['canonical'], '新增覆盖_度': str(r['gain']),
         '价格_CNY': str(r['price_n']),
         '性价比': str(r['gain'] / r['price_n']) if r['price_n'] else '免费'}
        for r in selected
    ]
    return {
        'fused_coverage': [[str(a), str(z)] for a, z in fused_coverage],
        'fused_width': str(length(fused_coverage)),
        'gap_rows': gap_rows,
        'gap_width': str(length(gaps)),
        'coverage_pct': str((20 - length(gaps)) * 5),
        'purchase_rows': purchase_rows,
        'purchase_scenes': len(selected),
        'purchase_cost': str(cost),
        'purchase_coverage': str(length(covered)),
        'ledger': ledger,
        'balanced': length(fused_coverage) + length(gaps) == Decimal(20),
    }
