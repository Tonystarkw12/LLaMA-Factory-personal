#!/usr/bin/env python3
"""Read-only verification of reviewed DB metadata and associated GRPO release."""
import argparse,collections,hashlib,importlib.util,json,math,sys
from dataclasses import fields
from pathlib import Path
A=Path('/mnt/d1/tony/outputs/pulse_db_followup_20260923')
D=Path('/mnt/d1/tony/outputs/grpo_data')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return [json.loads(l) for l in p.open()]
def dumps(x):return json.dumps(x,sort_keys=True,default=str)
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',default='clean_v4');args=p.parse_args()
 before={r['id']:r for r in rows(A/'database_before.jsonl')};after={r['id']:r for r in rows(A/'database_after.jsonl')}
 plan=json.load((A/'repair_plan.json').open());planned={r['id']:r for r in plan['records']}
 assert sha(A/'database_before.jsonl')==plan['snapshot_sha256']
 ingest=module('verified_ingest','/home/tony/NMRagent/backend/nmr/ingestion/v2.py');db=module('verified_db','/home/tony/NMRagent/.agents/skills/_PULSE_SEQUENCE_DB/Tools/PulseSequenceDb.py')
 c=db.connect();c.set_session(readonly=True,isolation_level='REPEATABLE READ')
 with c.cursor() as q:
  q.execute('SELECT * FROM public.nmr_pulse_sequences_v2 ORDER BY id');live={r['id']:dict(r) for r in q.fetchall()}
  q.execute('SELECT * FROM public.nmr_sequence_embeddings WHERE sequence_id=ANY(%s) ORDER BY id',(list(planned),));emb={r['id']:dict(r) for r in q.fetchall()}
 c.close();assert dumps(live)==dumps(after) and set(live)==set(before)
 for i,row in live.items():
  assert row['raw_code']==before[i]['raw_code'] and row['conflicts']==before[i]['conflicts']
  assert hashlib.sha256(row['raw_code'].encode()).hexdigest()==row['content_sha256']
  if i not in planned:assert dumps(row)==dumps(before[i]);continue
  ignore={'updated_at','search_vector'};want=planned[i]['after']
  assert dumps({k:v for k,v in row.items() if k not in ignore})==dumps({k:v for k,v in want.items() if k not in ignore}),i
 decisions=json.load((A/'proposal_review.json').open())['decisions'];decision_counts=collections.Counter()
 for d in decisions:
  decision_counts[d['decision']]+=1;r=live[d['id']]
  if d['decision']=='reject':
   assert r['nuclei']==before[d['id']]['nuclei'] if d['field']=='nuclei' else r['experiment_type']==before[d['id']]['experiment_type']
   continue
  expected=d['new'];key='nuclei' if d['field']=='nuclei' else 'family'
  if key=='family' and isinstance(expected,str) and ' + ' in expected:expected=expected.split(' + ')
  assert dumps(r['nuclei'] if key=='nuclei' else r['canonical_facts']['family'])==dumps(expected)
  for ev in d['evidence']:assert r['raw_code'].splitlines()[ev['line']-1].strip()==ev['text'].strip()
 results={r['id']:r for r in rows(A/'embedding_refresh_results.jsonl')};backup={r['id']:r for r in json.load((A/'embeddings_before.json').open())};assert set(emb)==set(backup)
 counts=collections.Counter()
 for i,e in emb.items():
  r=live[e['sequence_id']];rec=ingest.CanonicalRecord(**{f.name:r[f.name] for f in fields(ingest.CanonicalRecord)});doc=next(x for x in ingest.build_retrieval_documents(rec) if x.view==e['view_type'])
  assert (doc.text,doc.document_hash,doc.document_version)==(e['document_text'],e['document_hash'],e['document_version'])
  counts[e['sequence_id']]+=1
  if i not in results:assert dumps(e)==dumps(backup[i]);continue
  wanted=results[i];actual=json.loads(e['embedding']) if isinstance(e['embedding'],str) else list(e['embedding'])
  assert len(actual)==4096 and len(wanted['embedding'])==4096
  assert all(math.isfinite(x) and math.isclose(x,y,rel_tol=1e-6,abs_tol=1e-8) for x,y in zip(actual,wanted['embedding']))
 assert all(v==4 for v in counts.values())
 out=D/args.dataset;protected={'id','instruction','input','output','static','ref_timeline'};splitcounts={};fieldcounts=collections.Counter();changedrows=0
 for split in ('train','validation','test'):
  old=rows(D/'clean_v3'/f'{split}.jsonl');new=rows(out/f'{split}.jsonl');assert len(old)==len(new)
  for b,a in zip(old,new):
   assert {k:a.get(k) for k in protected}=={k:b.get(k) for k in protected},a['id']
   changed={k for k in set(a)|set(b) if a.get(k)!=b.get(k)};assert changed<={'family','db_meta','ref_prodopy','ref_sleepy','task_name','engine_support','reward_readiness'}
   fieldcounts.update(changed);changedrows+=bool(changed)
   if a.get('db_meta'):
    meta=json.loads(a['db_meta']);assert meta['matched_by']!='name'
    if meta['matched_by']=='exact_code_strip':
     match=live[meta['matched_db_id']];assert match['raw_code'].strip()==a['output'].strip()
     assert meta['dim']==match['dimension'] and meta['nuclei']==match['nuclei']
     f=match['canonical_facts']['family'];assert meta['type']==(f if isinstance(f,list) else [match['experiment_type']])
    elif meta['matched_by']=='unverified_name_only_variant':assert meta['matched_db_id'] is None and meta['historical_candidate_db_meta']
  splitcounts[split]={'rows':len(new),'sha256':sha(out/f'{split}.jsonl')}
 for filename in ('row_manifest.jsonl','excluded_quarantine.jsonl','cross_stage_exposure.json','static_dim_repairs.jsonl'):
  assert sha(D/'clean_v3'/filename)==sha(out/filename)
 report={'status':'PASS','database_rows':len(live),'modified_database_rows':len(planned),'raw_code_and_legacy_conflicts_preserved':True,'independent_review_decisions_checked':dict(decision_counts),'embedding_views_verified':len(emb),'new_vectors_verified':len(results),'splits':splitcounts,'dataset_changed_rows':changedrows,'changed_fields':dict(fieldcounts),'protected_program_prompt_static_timeline_order_unchanged':True,'remaining_db_unknown':sum(r['experiment_type']=='unknown' for r in live.values()),'remaining_db_empty_nuclei':sum(not r['nuclei'] for r in live.values()),'script_sha256':sha(Path(__file__))}
 (A/f'verification_{args.dataset}.json').write_text(json.dumps(report,indent=2)+'\n');(out/'database_and_metadata_verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
