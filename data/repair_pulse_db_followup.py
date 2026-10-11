#!/usr/bin/env python3
"""Audit-backed metadata-only PostgreSQL repair with atomic vector refresh.

No connection secrets are serialized. Raw programs, ids,
quality scores and unrelated metadata are not modified. An existing snapshot
is mandatory; live rows and vectors are checked before every transactional write.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
import os
import sys
import urllib.request
from dataclasses import fields
from pathlib import Path

ROOT=Path('/mnt/d1/tony/outputs/pulse_db_followup_20260923')
SKILL=Path('/home/tony/NMRagent/.agents/skills/_PULSE_SEQUENCE_DB/Tools/PulseSequenceDb.py')
INGEST=Path('/home/tony/NMRagent/backend/nmr/ingestion/v2.py')
MODEL='ryanshillington/Qwen3-Embedding-8B:latest'
TAG='reviewed_metadata_followup_20260923'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod


def dumps(value):return json.dumps(value,ensure_ascii=False,default=str,sort_keys=True)


def secure_write(path,value):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as handle:
        handle.write(dumps(value)+'\n')


def record(mod,row):
    return mod.CanonicalRecord(**{f.name:row[f.name] for f in fields(mod.CanonicalRecord)})


def prepare():
    mod=module('metadata_ingest',INGEST)
    source=[json.loads(line) for line in (ROOT/'database_before.jsonl').open()]
    proposals=[]
    reviews=json.loads((ROOT/'proposal_review.json').read_text())['decisions']
    accepted={d['id']:d for d in reviews if d['decision']!='reject'}
    conflict_rows={r['id']:r for r in json.loads((ROOT/'conflicts_analysis.json').read_text())['conflicts']}
    for before in source:
        after=copy.deepcopy(before);reasons=[]
        reviewed=mod.reviewed_source_evidence(before['raw_code'])
        for field,evidence in reviewed.items():
            value=evidence.value
            if field=='family':
                after['canonical_facts']['family']=value
                after['experiment_type']=mod.normalize_experiment_type(value)
                after['canonical_facts']['experiment_type']=after['experiment_type']
            elif field=='nuclei':
                after['nuclei']=list(value)
                after['canonical_facts']['nuclei']=list(value)
            else:raise AssertionError(field)
            after['provenance'].setdefault('fields',{})[field]={'source':evidence.source,'evidence':list(evidence.evidence)}
            reasons.append('independently_reviewed_'+field)
        declaration=mod.extract_dimension_metadata(before['raw_code'])
        if declaration['dimension_status']=='header_statement_derived':
            after['dimension']=declaration['dimension']
            after['canonical_facts'].update({k:v for k,v in declaration.items() if k!='evidence'})
            after['provenance'].setdefault('fields',{})['dimension']={
                'source':'standalone header dimension statement','evidence':declaration['evidence']}
            reasons.append('complete_standalone_header_dimension')
        if before['id'] in conflict_rows:
            # Preserve every legacy conflict. Store adjudication separately and do
            # not claim all disagreements are resolved or remove quality penalties.
            entries=copy.deepcopy(conflict_rows[before['id']]['entries'])
            decision=accepted.get(before['id'])
            for entry in entries:
                if decision and entry['field']=='family':
                    entry['applied_review']={'decision':decision['decision'],'value':after['canonical_facts']['family'],'reason':decision['reason']}
                entry['review_scope']='source metadata only; original conflict retained'
            after['provenance']['conflict_review']={'review':TAG,'entries':entries}
            reasons.append('classify_legacy_conflicts_with_evidence')
        if not reasons:continue
        after['provenance'].setdefault('metadata_repairs',[]).append(dict(
            repair=TAG,reasons=reasons,backup='database_before.jsonl',
            note='Reviewed source metadata only; raw program and original conflict records preserved.'))
        proposals.append(dict(id=before['id'],filename=before['filename'],before=before,after=after,reasons=reasons))
    secure_write(ROOT/'repair_plan.json',dict(
        snapshot_sha256=hashlib.sha256((ROOT/'database_before.jsonl').read_bytes()).hexdigest(),
        ingest_sha256=hashlib.sha256(INGEST.read_bytes()).hexdigest(),
        reviewed_sha256=hashlib.sha256(INGEST.with_name('reviewed_metadata.json').read_bytes()).hexdigest(),
        records=proposals))
    db=module('metadata_db',SKILL);conn=db.connect();conn.set_session(readonly=True)
    with conn.cursor() as cursor:
        cursor.execute('SELECT * FROM public.nmr_sequence_embeddings WHERE sequence_id = ANY(%s) ORDER BY id',
                       ([p['id'] for p in proposals],))
        embeddings=[dict(r) for r in cursor.fetchall()]
    conn.close()
    secure_write(ROOT/'embeddings_before.json',embeddings)
    by_id={p['id']:p for p in proposals}; jobs=[]
    for embedding in embeddings:
        p=by_id[embedding['sequence_id']]
        old_docs={doc.view:doc for doc in mod.build_retrieval_documents(record(mod,p['before']))}
        new_docs={doc.view:doc for doc in mod.build_retrieval_documents(record(mod,p['after']))}
        view=embedding['view_type'];old=old_docs[view];new=new_docs[view]
        assert embedding['document_version']==old.document_version
        assert embedding['document_text']==old.text and embedding['document_hash']==old.document_hash, (p['id'],view,'old-document mismatch')
        if old.text==new.text:continue
        assert embedding['embedding_model']==MODEL and embedding['model_dimension']==4096
        jobs.append(dict(id=embedding['id'],sequence_id=p['id'],view_type=view,
                         document_text=new.text,document_hash=new.document_hash,
                         document_version=new.document_version))
    secure_write(ROOT/'embedding_refresh_jobs.json',jobs)
    print(dumps(dict(proposed_records=len(proposals),embedding_refresh_jobs=len(jobs))),flush=True)


def embed():
    jobs=json.loads((ROOT/'embedding_refresh_jobs.json').read_text())
    path=ROOT/'embedding_refresh_results.jsonl'
    completed={r['id'] for r in (map(json.loads,path.open()) if path.exists() else [])}
    pending=[r for r in jobs if r['id'] not in completed]
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600),'a') as handle:
        for start in range(0,len(pending),4):
            batch=pending[start:start+4]
            payload=json.dumps(dict(model=MODEL,input=[j['document_text'] for j in batch],truncate=False)).encode()
            req=urllib.request.Request('http://localhost:11435/api/embed',data=payload,
                                       headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as response:
                result=json.load(response)
            vectors=result['embeddings'];assert len(vectors)==len(batch)
            for job,vector in zip(batch,vectors):
                assert len(vector)==4096 and all(math.isfinite(v) for v in vector)
                handle.write(dumps(dict(**job,embedding=vector))+'\n')
            handle.flush()
            print(dumps(dict(embedded=min(start+4,len(pending))+len(completed),total=len(jobs))),flush=True)


def apply():
    from psycopg2.extras import Json
    plan=json.loads((ROOT/'repair_plan.json').read_text());proposals=plan['records']
    assert hashlib.sha256(INGEST.read_bytes()).hexdigest()==plan['ingest_sha256'], 'ingestion changed after prepare'
    assert hashlib.sha256((ROOT/'database_before.jsonl').read_bytes()).hexdigest()==plan['snapshot_sha256'], 'backup changed'
    assert hashlib.sha256(INGEST.with_name('reviewed_metadata.json').read_bytes()).hexdigest()==plan['reviewed_sha256'], 'review changed'
    jobs=json.loads((ROOT/'embedding_refresh_jobs.json').read_text())
    results=[json.loads(line) for line in (ROOT/'embedding_refresh_results.jsonl').open()]
    assert len(results)==len(jobs) and {j['id'] for j in jobs}=={r['id'] for r in results}
    wanted={j['id']:j for j in jobs}
    for r in results:
        assert {k:v for k,v in r.items() if k!='embedding'}==wanted[r['id']]
        assert len(r['embedding'])==4096 and all(math.isfinite(v) for v in r['embedding'])
    backup={r['id']:r for r in json.loads((ROOT/'embeddings_before.json').read_text())}
    db=module('metadata_db',SKILL);conn=db.connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='10s'")
            cursor.execute("SET LOCAL statement_timeout='60s'")
            cursor.execute('SELECT * FROM public.nmr_pulse_sequences_v2 WHERE id=ANY(%s) ORDER BY id FOR UPDATE',
                           ([p['id'] for p in proposals],))
            live={r['id']:dict(r) for r in cursor.fetchall()}
            assert len(live)==len(proposals)
            for p in proposals:
                assert dumps(live[p['id']])==dumps(p['before']), (p['id'],'concurrent row change')
                a=p['after']
                cursor.execute('UPDATE public.nmr_pulse_sequences_v2 SET experiment_type=%s, dimension=%s, nuclei=%s, canonical_facts=%s, provenance=%s, updated_at=now() WHERE id=%s',
                               (a['experiment_type'],a['dimension'],a['nuclei'],Json(a['canonical_facts']),Json(a['provenance']),p['id']))
                assert cursor.rowcount==1
            cursor.execute('SELECT * FROM public.nmr_sequence_embeddings WHERE id=ANY(%s) ORDER BY id FOR UPDATE',
                           ([r['id'] for r in results],))
            live_vectors={r['id']:dict(r) for r in cursor.fetchall()}
            for r in results:
                assert dumps(live_vectors[r['id']])==dumps(backup[r['id']]),(r['id'],'concurrent vector change')
                cursor.execute('UPDATE public.nmr_sequence_embeddings SET document_text=%s,document_hash=%s,document_version=%s,embedding=%s::vector WHERE id=%s',
                               (r['document_text'],r['document_hash'],r['document_version'],json.dumps(r['embedding']),r['id']))
                assert cursor.rowcount==1
        conn.commit()
    except BaseException:
        conn.rollback();raise
    finally:conn.close()
    secure_write(ROOT/'apply_receipt.json',dict(status='COMMITTED',records=len(proposals),
        embeddings=len(results),transaction='metadata and refreshed vectors committed atomically',
        raw_code_edited=False,plan_sha256=hashlib.sha256((ROOT/'repair_plan.json').read_bytes()).hexdigest()))
    print('COMMITTED',len(proposals),'metadata records and',len(results),'embeddings')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('step',choices=['prepare','embed','apply'])
    globals()[parser.parse_args().step]()
