import sqlite3, json, os
from pathlib import Path
from app.errors import DomainError


def connection():
    path = Path(os.environ.get('APP_DB', 'data/runs.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核", fusion_status TEXT NOT NULL DEFAULT "待确认", confirmed_payload TEXT)')
    # 旧库迁移：新列与台账表（幂等）
    existing = {r[1] for r in db.execute('PRAGMA table_info(runs)')}
    if 'fusion_status' not in existing:
        db.execute('ALTER TABLE runs ADD COLUMN fusion_status TEXT NOT NULL DEFAULT "待确认"')
    if 'confirmed_payload' not in existing:
        db.execute('ALTER TABLE runs ADD COLUMN confirmed_payload TEXT')
    db.execute('''CREATE TABLE IF NOT EXISTS purchase_ledger(
        run_id TEXT NOT NULL, scene TEXT NOT NULL, price TEXT NOT NULL,
        gain TEXT NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY(run_id, scene))''')
    return db


def _view(row):
    view = {**json.loads(row['payload']), 'revision': row['revision'],
            'decision': row['decision'], 'fusion_status': row['fusion_status']}
    if row['confirmed_payload']:
        view['confirmed'] = json.loads(row['confirmed_payload'])
    return view


def save(result):
    with connection() as db:
        ident = result['manifest']['run_id']
        row = db.execute('SELECT * FROM runs WHERE id=?', (ident,)).fetchone()
        if row:
            return {**_view(row), 'reused': True}
        db.execute('INSERT INTO runs(id,payload) VALUES (?,?)',
                   (ident, json.dumps(result, ensure_ascii=False)))
        row = db.execute('SELECT * FROM runs WHERE id=?', (ident,)).fetchone()
    return {**_view(row), 'reused': False}


def get_run(ident):
    with connection() as db:
        row = db.execute('SELECT * FROM runs WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise DomainError('NOT_FOUND', '批次不存在', 404)
        return _view(row)


def latest():
    with connection() as db:
        row = db.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
        return _view(row) if row else None


def history():
    with connection() as db:
        return [{'id': r['id'], 'revision': r['revision'], 'decision': r['decision'],
                 'fusion_status': r['fusion_status']}
                for r in db.execute('SELECT * FROM runs ORDER BY rowid DESC')]


def review(ident, revision, decision):
    if decision not in ('通过', '退回'):
        raise DomainError('DECISION', '复核动作无效')
    with connection() as db:
        changed = db.execute('UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?',
                             (decision, ident, revision)).rowcount
        if not changed:
            raise DomainError('VERSION', '版本已变化，请重新载入', 409)
    return {'revision': revision + 1, 'decision': decision}


def confirm_fusion(ident, revision, decision, fault=None):
    """确认/退回融合提案。整个重算与写入在单事务内完成，任何异常整体回滚到旧版。

    fault 仅供测试：在事务提交前注入中断，验证旧版完整恢复。
    """
    if decision not in ('已确认', '已退回'):
        raise DomainError('DECISION', '融合动作无效')
    from app.modules.m8_fusion.confirm import derive_confirmed
    with connection() as db:
        try:
            row = db.execute('SELECT * FROM runs WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise DomainError('NOT_FOUND', '批次不存在', 404)
            if row['revision'] != revision:
                raise DomainError('VERSION', '版本已变化，请重新载入', 409)
            if row['fusion_status'] != '待确认':
                raise DomainError('FUSION_STATE', '该批次融合已确认，不可重复确认', 409)
            if fault is not None:  # 测试注入：提交前中断，触发整体回滚
                raise RuntimeError(fault)
            payload = json.loads(row['payload'])
            if decision == '已确认':
                confirmed = derive_confirmed(payload)
                # 台账写入带 PRIMARY KEY(run_id,scene) 唯一约束：同批次重试不会新增采购
                for item in confirmed['ledger']:
                    db.execute('INSERT OR IGNORE INTO purchase_ledger(run_id,scene,price,gain,evidence) VALUES (?,?,?,?,?)',
                               (ident, item['场景'], item['价格_CNY'], item['新增覆盖_度'],
                                json.dumps(item['来源观测'], ensure_ascii=False)))
                db.execute('UPDATE runs SET revision=revision+1,fusion_status=?,confirmed_payload=? WHERE id=? AND revision=?',
                           (decision, json.dumps(confirmed, ensure_ascii=False), ident, revision))
            else:
                db.execute('UPDATE runs SET revision=revision+1,fusion_status=? WHERE id=? AND revision=?',
                           (decision, ident, revision))
            ledger_count = db.execute('SELECT COUNT(*) AS n FROM purchase_ledger WHERE run_id=?', (ident,)).fetchone()['n']
        except Exception:
            db.rollback()
            raise
    return {'revision': revision + 1, 'fusion_status': decision, 'ledger_scenes': ledger_count}


def ledger(ident):
    with connection() as db:
        rows = db.execute('SELECT * FROM purchase_ledger WHERE run_id=? ORDER BY rowid', (ident,)).fetchall()
        return [{'场景': r['scene'], '价格_CNY': r['price'], '新增覆盖_度': r['gain'],
                 '来源观测': json.loads(r['evidence'])} for r in rows]
