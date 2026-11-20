from decimal import Decimal

from app.domain import claim_parts, length
from app.numeric import number
from app.config import FUSION_SAMPLE
from app.pipeline import calculate
from app.modules.m8_fusion.rules import apply as fusion_apply
from app.modules.m8_fusion.confirm import derive_confirmed


def _demo():
    return calculate(FUSION_SAMPLE.read_text(encoding='utf-8-sig'))


def test_claim_parts_single_owner_per_segment():
    offer = [((-1, 2), [(Decimal(0), Decimal(10))]), ((-2, 5), [(Decimal(3), Decimal(8))])]
    parts = claim_parts(offer)
    # 每个经度点只归属一个来源，段宽之和等于并集宽度
    assert length([span for span, _ in parts]) == Decimal(10)
    owners = {span: key for span, key in parts}
    assert owners[(0, 3)] == (-1, 2) and owners[(3, 8)] == (-2, 5) and owners[(8, 10)] == (-1, 2)


def test_claim_parts_deterministic_tie_break():
    a = [((-1, 1), [(Decimal(0), Decimal(5))])]
    b = [((-1, 2), [(Decimal(0), Decimal(5))])]
    assert claim_parts(a + b) == claim_parts(list(reversed(a + b)))


def test_proposal_segments_trace_to_source_and_time():
    ctx = _demo()
    segments = ctx['stages']['8']['rows']
    required = {'融合场景', '融合起点', '融合终点', '来源场景', '来源行号', '来源版本', '采集时间', '来源角色'}
    assert required.issubset(segments[0])
    # FUSE-A 的 170-171 必须来自 v1（历史过境），可追到行号与采集时间
    a170 = next(s for s in segments if s['融合场景'] == 'FUSE-A' and s['融合起点'] == '170')
    assert a170['来源版本'] == 1 and a170['采集时间'] == '2026-11-10T00:00:00Z' and a170['来源行号'] == 2


def test_proposal_does_not_mutate_baseline_gap_or_purchase():
    ctx = _demo()
    # 确认前缺口仍是基线口径（170-175 是基线缺口的一部分）
    gap_spans = [(number(a), number(z)) for a, z in [(g['缺口起点'], g['缺口终点']) for g in ctx['stages']['5']['rows']]]
    assert (Decimal(170), Decimal(175)) in gap_spans
    assert number(ctx['fusion_proposal']['gain']) > 0
    # 基线覆盖不被提案改写：演示数据基线覆盖8°，融合后14°
    assert length([(number(a), number(z)) for a, z in ctx['coverage']]) == number('8')


def test_excluded_rows_carry_reasons():
    ctx = _demo()
    excluded = ctx['stages']['8']['excluded_rows']
    codes = {e['原因码'] for e in excluded}
    assert {'FUSE_CLOUD', 'FUSE_REDUNDANT', 'FUSE_BASELINE'}.issubset(codes)
    # FUSE-A v3 全云、FUSE-C v2 全云
    assert any(e['融合场景'] == 'FUSE-A' and e['原因码'] == 'FUSE_CLOUD' for e in excluded)
    # 贡献了独有段的历史过境不出现在未融合表
    assert not any(e['融合场景'] == 'FUSE-A' and e['来源版本'] == 1 for e in excluded)


def test_quality_failed_transit_is_excluded_not_used():
    ctx = _demo()
    segments = ctx['stages']['8']['rows']
    # FUSE-D v2 质量失败，其任何段不得被采信
    assert all(not (s['融合场景'] == 'FUSE-D' and s['来源版本'] == 2) for s in segments)


def test_derived_confirmed_view_closes_gaps_and_counts_scene_once():
    ctx = _demo()
    confirmed = derive_confirmed(ctx)
    # 融合后 170-171、173-175 等缺口被补上，缺口由 12° 降到 6°
    assert number(confirmed['gap_width']) == number('6')
    assert number(confirmed['fused_width']) == number('14')
    assert confirmed['balanced'] is True
    # 每个场景在采购台账中只出现一次，即使融合了多个过境
    scenes = [item['场景'] for item in confirmed['ledger']]
    assert len(scenes) == len(set(scenes)) == 4
    # 台账条目保留每个场景的全部来源观测证据
    fuse_a = next(item for item in confirmed['ledger'] if item['场景'] == 'FUSE-A')
    assert {s['来源版本'] for s in fuse_a['来源观测']} == {1, 2}


def test_default_sample_has_no_fusion_gain():
    # 主样例全部为单次过境，融合不应凭空增加覆盖
    ctx = calculate()
    assert number(ctx['fusion_proposal']['gain']) == 0
    assert ctx['stages']['8']['metrics'][2][1] == 0


def test_fusion_apply_is_pure_on_coverage(ctx):
    before = list(ctx['coverage'])
    fusion_apply(ctx)
    assert ctx['coverage'] == before
