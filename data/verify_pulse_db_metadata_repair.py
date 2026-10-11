#!/usr/bin/env python3
"""Independent read-only checks of pulse metadata repair and GRPO propagation.

Uses stored program declarations, not the changed ingestion parser. Does not
import repair scripts, mutate PostgreSQL, or generate corrected metadata.
"""
import argparse
import ast
import collections
import hashlib
import json
import math
import os
import re
from pathlib import Path

AUDIT=Path('/mnt/d1/tony/outputs/pulse_db_audit_20260923')
GRPO=Path('/mnt/d1/tony/outputs/grpo_data')

def js(x):return json.dumps(x,sort_keys=True,default=str,ensure_ascii=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return [json.loads(line) for line in p.open()]
def check(ok,message):
    if not ok:raise AssertionError(message)
def write(name,data):
    (AUDIT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

def declarations(code):
    return re.findall(r'^\s*;\s*\$DIM\s*=([^\r\n]*)',code,re.M|re.I)

def preflight():
    before={r['id']:r for r in rows(AUDIT/'database_before.jsonl')}
    plan=json.loads((AUDIT/'repair_plan.json').read_text())
    check(sha(AUDIT/'database_before.jsonl')==plan['snapshot_sha256'],'snapshot hash')
    planned={r['id']:r for r in plan['records']}
    type_ids=set();special_ids=set();numeric=[]
    for i,r in before.items():
        check(hashlib.sha256(r['raw_code'].encode()).hexdigest()==r['content_sha256'],f'raw hash {i}')
        if r['experiment_type'].startswith('['):type_ids.add(i)
        ds=declarations(r['raw_code'])
        if any('pseudo' in d.lower() or len(set(re.findall(r'([1-7])\s*D',d,re.I)))>1 for d in ds):special_ids.add(i)
    check(set(planned)==type_ids|special_ids,'unexpected proposed record set')
    for i,p in planned.items():
        b,a=p['before'],p['after']
        check(b==before[i],f'plan before {i}')
        changed={k for k in b if b[k]!=a[k]}
        check(changed <= {'experiment_type','dimension','canonical_facts','provenance'},f'forbidden field {i}: {changed}')
        check(a['canonical_facts']['family']==b['canonical_facts']['family'],f'family retained {i}')
        if i in type_ids:
            expected=' + '.join(ast.literal_eval(b['experiment_type']))
            check(a['experiment_type']==expected and a['canonical_facts']['experiment_type']==expected,f'compound type {i}')
        if i in special_ids:
            ds=declarations(a['raw_code']);check(len(ds)==1,f'special headers {i}')
            values=sorted(set(int(v) for v in re.findall(r'([1-7])\s*D',ds[0],re.I)))
            expected=values[0] if len(values)==1 else None
            check(a['dimension']==expected,f'special dimension {i}')
            f=a['canonical_facts']
            check(f['dimension']==expected and f['dimension_candidates']==values,f'canonical dimension {i}')
            check(f['dimension_is_pseudo']==('pseudo' in ds[0].lower()),f'pseudo {i}')
            check(f['dimension_declarations']==[ds[0].strip()],f'declaration retained {i}')
        if a['dimension']!=b['dimension']:numeric.append({'id':i,'filename':a['filename'],'before':b['dimension'],'after':a['dimension']})
    jobs=json.loads((AUDIT/'embedding_refresh_jobs.json').read_text())
    emb=json.loads((AUDIT/'embeddings_before.json').read_text())
    check(len(emb)==4*len(planned),'all four embedding views backed up')
    for j in jobs:
        check(j['sequence_id'] in planned,'embedding job associated')
        expected=hashlib.sha256(f"{j['document_version']}\0{j['view_type']}\0{j['document_text']}".encode()).hexdigest()
        check(j['document_hash']==expected,'embedding job hash')
        check(j['view_type']!='source','source embedding should not change')
    result={'status':'PASS','records':len(before),'planned_records':len(planned),'compound_types':len(type_ids),'special_declarations':len(special_ids),'numeric_dimension_changes':numeric,'embedding_jobs':len(jobs),'embedding_views_backed_up':len(emb),'independent_declaration_parser':True}
    write('independent_repair_preflight.json',result)
    return result

def verify_live():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    before={r['id']:r for r in rows(AUDIT/'database_before.jsonl')}
    plan=json.loads((AUDIT/'repair_plan.json').read_text());planned={r['id']:r for r in plan['records']}
    backups={r['id']:r for r in json.loads((AUDIT/'embeddings_before.json').read_text())}
    results={r['id']:r for r in rows(AUDIT/'embedding_refresh_results.jsonl')}
    check((AUDIT/'apply_receipt.json').exists(),'apply receipt missing')
    try:conn=psycopg2.connect(os.environ['PULSE_SEQUENCE_DB_URL'],cursor_factory=RealDictCursor)
    except Exception as err:raise RuntimeError(f'Database connection failed: {type(err).__name__}') from None
    conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
    with conn,conn.cursor() as cur:
        cur.execute('SELECT * FROM public.nmr_pulse_sequences_v2 ORDER BY id')
        live={r['id']:dict(r) for r in cur.fetchall()}
        cur.execute('SELECT * FROM public.nmr_sequence_embeddings WHERE sequence_id = ANY(%s) ORDER BY id',(list(planned),))
        vectors={r['id']:dict(r) for r in cur.fetchall()}
        cur.execute('SELECT count(*) AS n, count(DISTINCT sequence_id) AS sequences FROM public.nmr_sequence_embeddings')
        total=dict(cur.fetchone())
    conn.close()
    check(set(live)==set(before),'record ids preserved')
    for i,r in live.items():
        b=before[i]
        if i not in planned:check(js(r)==js(b),f'unplanned row changed {i}');continue
        expected=planned[i]['after']
        ignored={'updated_at','search_vector'}
        check(js({k:v for k,v in r.items() if k not in ignored})==js({k:v for k,v in expected.items() if k not in ignored}),f'applied row mismatch {i}')
        check(hashlib.sha256(r['raw_code'].encode()).hexdigest()==r['content_sha256'],f'live raw hash {i}')
    check(set(vectors)==set(backups),'embedding ids preserved')
    for i,v in vectors.items():
        b=backups[i]
        if i not in results:check(js(v)==js(b),f'unrequested vector changed {i}');continue
        wanted=results[i]
        for k in ('document_text','document_hash','document_version'):check(v[k]==wanted[k],f'vector text/hash {i} {k}')
        expected_hash=hashlib.sha256(f"{v['document_version']}\0{v['view_type']}\0{v['document_text']}".encode()).hexdigest()
        check(v['document_hash']==expected_hash,f'vector hash independent {i}')
        protected=set(b)-{'embedding','document_text','document_hash','document_version'}
        check(js({k:v[k] for k in protected})==js({k:b[k] for k in protected}),f'vector protected fields {i}')
        observed=json.loads(v['embedding']) if isinstance(v['embedding'],str) else list(v['embedding'])
        check(len(observed)==4096 and all(math.isfinite(x) for x in observed),f'vector finite4096 {i}')
        check(all(math.isclose(x,y,rel_tol=1e-6,abs_tol=1e-8) for x,y in zip(observed,wanted['embedding'])),f'vector values mismatch {i}')
    check(total=={'n':7448,'sequences':1862},'embedding population changed')
    return {'status':'PASS','live_rows':len(live),'changed_rows_verified':len(planned),'all_other_rows_unchanged':len(live)-len(planned),'embeddings_checked':len(vectors),'refreshed_vectors_checked':len(results),'embedding_total':total,'connection_readonly':True}

def verify_grpo():
    db=rows(AUDIT/'database_after.jsonl');by_code=collections.defaultdict(list)
    for r in db:by_code[r['raw_code'].strip()].append(r)
    parent=GRPO/'clean_v2';child=GRPO/'clean_v3';counts=collections.Counter();splits={}
    for split in ('train','validation','test'):
        old=rows(parent/f'{split}.jsonl');new=rows(child/f'{split}.jsonl')
        check(len(old)==len(new),f'GRPO row count {split}')
        for b,a in zip(old,new):
            check(set(a)==set(b),f'GRPO field set {b["id"]}')
            check({k:v for k,v in a.items() if k not in {'family','db_meta'}}=={k:v for k,v in b.items() if k not in {'family','db_meta'}},f'GRPO protected fields {b["id"]}')
            if a['family']!=b['family']:
                check(a['family']==' + '.join(ast.literal_eval(b['family'])),f'GRPO family {b["id"]}')
                counts['family_changes']+=1
            if not b.get('db_meta'):check(a.get('db_meta')==b.get('db_meta'),'metadata inserted');continue
            bm=json.loads(b['db_meta']);am=json.loads(a['db_meta'])
            check(am.get('nuclei')==bm.get('nuclei'),'GRPO nuclei changed')
            counts['db_meta_changes']+=am!=bm
            candidates=by_code.get(a['output'].strip(),[])
            sig={(r['dimension'],js(r['canonical_facts'].get('family')),r['experiment_type']) for r in candidates}
            if candidates and len(sig)==1:
                r=candidates[0];f=r['canonical_facts'];counts['matched']+=1
                check(am['dim']==r['dimension'],'GRPO dimension propagation')
                check(am['type']==(f['family'] if isinstance(f.get('family'),list) else [r['experiment_type']]),'GRPO family propagation')
                for k in ('dimension_label','dimension_candidates','dimension_is_pseudo','dimension_kind','dimension_declarations'):
                    if k in f:check(am[k]==f[k],'GRPO dimension declaration propagation')
            else:
                counts['unmatched']+=1
                check({k:v for k,v in am.items() if k!='type'}=={k:v for k,v in bm.items() if k!='type'},'unmatched scientific metadata changed')
            check(all(not (isinstance(v,str) and v.startswith('[')) for v in am['type']),'nested Python repr retained')
        splits[split]={'rows':len(new),'sha256':sha(child/f'{split}.jsonl'),'parent_sha256':sha(parent/f'{split}.jsonl')}
    for name in ('row_manifest.jsonl','excluded_quarantine.jsonl','cross_stage_exposure.json','build_stats.json','static_dim_repairs.jsonl'):
        check(sha(parent/name)==sha(child/name),f'lineage file changed {name}')
    return {'status':'PASS','splits':splits,'counts':dict(counts),'all_protected_fields_unchanged':True,'lineage_artifacts_byte_identical':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--preflight-only',action='store_true');args=parser.parse_args()
    report={'preflight':preflight()}
    if not args.preflight_only:
        report.update(live_database=verify_live(),grpo=verify_grpo())
        report.update(status='PASS',script_sha256=sha(Path(__file__)))
        write('independent_repair_verification.json',report)
    print(json.dumps(report,indent=2))
