from collections import Counter
from app.modules.m8_fusion.rules import apply
from app.numeric import serial


def execute(ctx):
    before = len(ctx['quarantine'])
    result = apply(ctx)
    result['stage'] = 8
    result['name'] = '融合确认'
    result['issues'] = dict(Counter(row['原因码'] for row in ctx['quarantine']))
    result['new_quarantine'] = len(ctx['quarantine']) - before
    ctx['stages']['8'] = serial(result)
    return ctx
