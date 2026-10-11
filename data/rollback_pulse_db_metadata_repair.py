#!/usr/bin/env python3
"""Guarded rollback for the metadata repair transaction; never overwrites drift."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path('/mnt/d1/tony/outputs/pulse_db_audit_20260923')
SKILL = Path('/home/tony/NMRagent/.agents/skills/_PULSE_SEQUENCE_DB/Tools/PulseSequenceDb.py')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def main():
    from psycopg2.extras import Json
    receipt = json.loads((ROOT / 'apply_receipt.json').read_text())
    assert receipt['status'] == 'COMMITTED'
    plan = json.loads((ROOT / 'repair_plan.json').read_text())
    after = {r['id']: r for r in (json.loads(line) for line in (ROOT / 'database_after.jsonl').open())}
    backup = {r['id']: r for r in json.loads((ROOT / 'embeddings_before.json').read_text())}
    results = [json.loads(line) for line in (ROOT / 'embedding_refresh_results.jsonl').open()]
    db = module('rollback_metadata_db', SKILL)
    conn = db.connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='10s'")
            cursor.execute("SET LOCAL statement_timeout='60s'")
            cursor.execute('SELECT * FROM public.nmr_pulse_sequences_v2 WHERE id=ANY(%s) ORDER BY id FOR UPDATE',
                           ([p['id'] for p in plan['records']],))
            live_rows = {r['id']: dict(r) for r in cursor.fetchall()}
            ids = [r['id'] for r in results]
            cursor.execute('SELECT * FROM public.nmr_sequence_embeddings WHERE id=ANY(%s) ORDER BY id FOR UPDATE', (ids,))
            live_vectors = {r['id']: dict(r) for r in cursor.fetchall()}
            assert len(live_rows) == len(plan['records'])
            for p in plan['records']:
                row = live_rows[p['id']]
                assert dumps(row) == dumps(after[p['id']]), (p['id'], 'row changed since after-snapshot')
                for key in ('experiment_type', 'dimension', 'canonical_facts', 'provenance'):
                    assert dumps(row[key]) == dumps(p['after'][key]), (p['id'], key, 'row changed since repair')
            for result in results:
                live = live_vectors[result['id']]
                assert live['sequence_id'] == result['sequence_id']
                assert live['document_text'] == result['document_text']
                assert live['document_hash'] == result['document_hash']
                assert live['document_version'] == result['document_version']
                old = backup[result['id']]
                assert live['embedding_model'] == old['embedding_model']
                assert live['model_dimension'] == old['model_dimension']
                vector = json.loads(live['embedding']) if isinstance(live['embedding'], str) else live['embedding']
                assert len(vector) == len(result['embedding'])
                assert all(abs(a-b) < 1e-6 for a, b in zip(vector, result['embedding'])), 'vector changed since repair'
                cursor.execute('UPDATE public.nmr_sequence_embeddings SET document_text=%s,document_hash=%s,document_version=%s,embedding=%s::vector WHERE id=%s',
                               (old['document_text'], old['document_hash'], old['document_version'], str(old['embedding']), result['id']))
            for p in plan['records']:
                old = p['before']
                cursor.execute('UPDATE public.nmr_pulse_sequences_v2 SET experiment_type=%s,dimension=%s,canonical_facts=%s,provenance=%s,updated_at=%s WHERE id=%s',
                               (old['experiment_type'], old['dimension'], Json(old['canonical_facts']), Json(old['provenance']), old['updated_at'], p['id']))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print('Rollback committed for', len(plan['records']), 'records and', len(results), 'embedding rows')


if __name__ == '__main__':
    main()
