from app.config import FUSION_SAMPLE


def _demo_run(client):
    csv_text = FUSION_SAMPLE.read_text(encoding='utf-8-sig')
    return client.post('/api/run', json={'csv': csv_text}).get_json()


def test_m8_endpoint_returns_proposal(client):
    resp = client.post('/api/m8', json={'csv': FUSION_SAMPLE.read_text(encoding='utf-8-sig')})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['stage'] == 8 and body['rows'] and body['excluded_rows']


def test_confirm_then_gap_and_purchase_update_once(client):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    assert run['fusion_status'] == '待确认'
    resp = client.post('/api/fusion/confirm', json={'id': ident, 'revision': 1, 'decision': '已确认'})
    assert resp.status_code == 200
    view = client.get('/api/runs/' + ident).get_json()
    assert view['fusion_status'] == '已确认' and view['revision'] == 2
    # 确认后缺口更新为融合口径（6°），采购台账同场景仅一次
    assert view['confirmed']['gap_width'] == '6'
    ledger = client.get('/api/fusion/ledger?run_id=' + ident).get_json()
    scenes = [r['场景'] for r in ledger]
    assert len(scenes) == len(set(scenes)) == 4


def test_retry_same_batch_adds_no_purchase(client):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    payload = {'id': ident, 'revision': 1, 'decision': '已确认'}
    assert client.post('/api/fusion/confirm', json=payload).status_code == 200
    # 陈旧revision重试：409，不新增采购
    stale = client.post('/api/fusion/confirm', json=payload)
    assert stale.status_code == 409 and stale.get_json()['code'] == 'VERSION'
    ledger = client.get('/api/fusion/ledger?run_id=' + ident).get_json()
    assert len(ledger) == 4
    # 已确认批次不可再次确认
    again = client.post('/api/fusion/confirm',
                        json={'id': ident, 'revision': 2, 'decision': '已确认'})
    assert again.status_code == 409 and again.get_json()['code'] == 'FUSION_STATE'
    assert len(client.get('/api/fusion/ledger?run_id=' + ident).get_json()) == 4


def test_reject_keeps_baseline_and_empty_ledger(client):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    resp = client.post('/api/fusion/confirm',
                       json={'id': ident, 'revision': 1, 'decision': '已退回'})
    assert resp.status_code == 200 and resp.get_json()['ledger_scenes'] == 0
    view = client.get('/api/runs/' + ident).get_json()
    assert view['fusion_status'] == '已退回' and 'confirmed' not in view
    assert client.get('/api/fusion/ledger?run_id=' + ident).get_json() == []


def test_interrupted_recompute_rolls_back_to_old_version(client, monkeypatch):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    client.application.config['PROPAGATE_EXCEPTIONS'] = False
    import app.main as main
    monkeypatch.setattr(main, 'confirm_fusion',
                        lambda i, r, d: _store_confirm_with_fault(i, r, d))
    resp = client.post('/api/fusion/confirm',
                       json={'id': ident, 'revision': 1, 'decision': '已确认'})
    assert resp.status_code == 500
    view = client.get('/api/runs/' + ident).get_json()
    assert view['revision'] == 1 and view['fusion_status'] == '待确认'
    assert 'confirmed' not in view
    assert client.get('/api/fusion/ledger?run_id=' + ident).get_json() == []


def _store_confirm_with_fault(ident, revision, decision):
    from app.store import confirm_fusion
    return confirm_fusion(ident, revision, decision, fault='simulated recompute crash')


def test_m8_page_renders_sources_and_reasons(client):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    html = client.get('/work/8?run_id=' + ident).data.decode()
    assert '融合确认' in html and '采集时间' in html and '未融合原因' in html
    assert 'FUSE_CLOUD' in html and ident in html


def test_evidence_includes_fusion_rows_and_ledger(client):
    run = _demo_run(client)
    ident = run['manifest']['run_id']
    client.post('/api/fusion/confirm', json={'id': ident, 'revision': 1, 'decision': '已确认'})
    text = client.get('/api/evidence.csv?run_id=' + ident).data.decode('utf-8-sig')
    assert '8-未融合' in text and '融合采购台账' in text and 'FUSE-A' in text


def test_fusion_sample_endpoint(client):
    text = client.get('/api/fusion/sample').data.decode('utf-8-sig')
    assert text.startswith('scene,alias') and 'FUSE-A' in text


def test_invalid_fusion_action_rejected(client):
    run = _demo_run(client)
    resp = client.post('/api/fusion/confirm',
                       json={'id': run['manifest']['run_id'], 'revision': 1, 'decision': '其他'})
    assert resp.status_code == 422 and resp.get_json()['code'] == 'DECISION'


def test_unknown_run_confirmation_is_404(client):
    resp = client.post('/api/fusion/confirm',
                       json={'id': 'absent', 'revision': 1, 'decision': '已确认'})
    assert resp.status_code == 404
