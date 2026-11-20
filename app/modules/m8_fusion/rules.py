from app.domain import intersect, subtract, TARGET, length, merge, claim_parts
from app.numeric import number


def _clear(r):
    if r['quality'] != 'pass':
        return []
    return intersect(subtract(r['spans'], r['cloud']), TARGET)


def apply(ctx):
    """多过境融合提案：只产出可确认的融合建议与未融合原因，不修改coverage/gaps。"""
    fused_segments = []
    excluded = []
    scene_count = 0
    extra_width = number(0)

    for canonical in sorted(ctx.get('transits', {})):
        items = ctx['transits'][canonical]
        quality_pass = [r for r in items if r['quality'] == 'pass']
        if not quality_pass:
            for r in items:
                excluded.append(_exclusion(r, canonical, 'FUSE_QUALITY', '影像质量未通过'))
            continue
        scene_count += 1
        winner = quality_pass[0]  # transits已按版本降序、行号升序排列
        offer = []
        for r in quality_pass:
            clear = _clear(r)
            if not clear:
                excluded.append(_exclusion(r, canonical, 'FUSE_CLOUD', '目标纬带内无清晰段'))
                continue
            # 排序键：版本降序（取负）、行号升序，保证确定性且最新过境优先
            offer.append(((-r['version_n'], r['行号']), clear, r))
        owned = claim_parts([(key, spans) for key, spans, _ in offer])
        row_by_key = {(-r['version_n'], r['行号']): r for _, _, r in offer}
        scene_extra = number(0)
        for (a, z), key in owned:
            source = row_by_key[key]
            is_base = source is winner
            fused_segments.append({
                '融合场景': canonical,
                '融合起点': str(a), '融合终点': str(z), '段宽度_度': str(z - a),
                '来源场景': source['scene'], '来源行号': source['行号'],
                '来源版本': source['version_n'], '采集时间': source['captured'],
                '来源角色': '基线（最新过境）' if is_base else '补充（历史过境）',
            })
            if not is_base:
                scene_extra += z - a
        # 未融合原因：仅记录未提供任何独有归属的过境；贡献了融合段的在融合段表中溯源
        owned_by_key = {key for _, key in owned}
        for key, _, r in offer:
            if r is winner:
                excluded.append(_exclusion(r, canonical, 'FUSE_BASELINE', '最新过境，已作为融合基线采信'))
                continue
            if key in owned_by_key:
                continue
            excluded.append(_exclusion(r, canonical, 'FUSE_REDUNDANT',
                                       '清晰段与已融合覆盖完全重叠，无独有补充'))
        extra_width += scene_extra

    # 融合后场景级覆盖（每个场景只出现一次，采购据此计一次）
    fused_by_scene = {}
    for seg in fused_segments:
        fused_by_scene.setdefault(seg['融合场景'], []).append(
            (number(seg['融合起点']), number(seg['融合终点'])))
    fused_scenes = [
        {'canonical': canonical, 'fused_clear': merge(spans)}
        for canonical, spans in sorted(fused_by_scene.items())
    ]
    fused_coverage = merge([s for r in fused_scenes for s in r['fused_clear']])
    baseline_coverage = ctx.get('coverage', [])
    gain = length(subtract(fused_coverage, baseline_coverage))

    ctx['fusion_proposal'] = {
        'segments': fused_segments,
        'excluded': excluded,
        'fused_scenes': [
            {**r, 'fused_clear': [[str(a), str(z)] for a, z in r['fused_clear']]}
            for r in fused_scenes
        ],
        'fused_coverage': [[str(a), str(z)] for a, z in fused_coverage],
        'gain': str(gain),
    }

    metrics = [
        ['参与融合场景', scene_count, '个'],
        ['融合段数', len(fused_segments), '段'],
        ['补充清晰段', sum(1 for s in fused_segments if s['来源角色'].startswith('补充')), '段'],
        ['新增覆盖_度', str(gain), '度'],
        ['未融合记录', len(excluded), '条'],
    ]
    return {'rows': fused_segments, 'excluded_rows': excluded, 'metrics': metrics}


def _exclusion(r, canonical, code, detail):
    return {
        '融合场景': canonical, '来源场景': r['scene'], '来源行号': r['行号'],
        '来源版本': r['version_n'], '采集时间': r['captured'],
        '原因码': code, '原因': detail,
    }
