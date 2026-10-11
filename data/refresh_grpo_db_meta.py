#!/usr/bin/env python3
"""Propagate confirmed DB corrections; preserve raw programs and GRPO splits."""
import ast
import collections
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path('/mnt/d1/tony/outputs/grpo_data')
AUDIT=Path('/mnt/d1/tony/outputs/pulse_db_audit_20260923')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def labels(values):
    result=[]
    for value in values:
        if isinstance(value,str) and value.startswith('['):
            try:parsed=ast.literal_eval(value)
            except (SyntaxError,ValueError):parsed=None
            if isinstance(parsed,list) and parsed and all(isinstance(x,str) and x for x in parsed):
                result.extend(parsed);continue
        result.append(value)
    return list(dict.fromkeys(result))


def main():
    source=ROOT/'clean_v2';out=ROOT/'clean_v3'
    out.mkdir(exist_ok=False)
    db=[json.loads(line) for line in (AUDIT/'database_after.jsonl').open()]
    by_code=collections.defaultdict(list)
    for r in db:by_code[r['raw_code'].strip()].append(r)
    repairs=[];queue=[];files={};counts=collections.Counter()
    for split in ('train','validation','test'):
        rows=[json.loads(line) for line in (source/f'{split}.jsonl').open()]
        with (out/f'{split}.jsonl').open('x') as handle:
            for n,r in enumerate(rows,1):
                original=copy.deepcopy(r)
                if r.get('db_meta'):
                    meta=json.loads(r['db_meta']);before=copy.deepcopy(meta)
                    meta['type']=labels(meta.get('type',[]))
                    candidates=by_code.get(r['output'].strip(),[])
                    signature={(d['dimension'],json.dumps(d['canonical_facts'].get('family')),d['experiment_type']) for d in candidates}
                    match=candidates[0] if candidates and len(signature)==1 else None
                    if match:
                        facts=match['canonical_facts']
                        family=facts.get('family')
                        meta['type']=family if isinstance(family,list) else [match['experiment_type']]
                        meta['dim']=match['dimension']
                        for key in ('dimension_label','dimension_candidates','dimension_is_pseudo','dimension_kind','dimension_declarations'):
                            if key in facts:meta[key]=facts[key]
                        # Nuclei differences require domain review, not automatic replacement.
                        if set(meta.get('nuclei',[]))!=set(match['nuclei']):
                            queue.append(dict(split=split,line=n,id=r['id'],issue='nuclei_disagreement',db_id=match['id'],
                                              grpo_nuclei=meta.get('nuclei'),db_nuclei=match['nuclei']))
                        counts['db_exact_body_matched']+=1
                    else:
                        queue.append(dict(split=split,line=n,id=r['id'],issue='no_unique_exact_body_db_match'))
                        counts['unresolved_db_match']+=1
                    if meta!=before:
                        r['db_meta']=json.dumps(meta,ensure_ascii=False)
                        repairs.append(dict(split=split,line=n,id=r['id'],before=before,after=meta,
                                            db_id=match['id'] if match else None,
                                            matching='exact_code_strip' if match else 'serialization_only'))
                        counts['db_meta_changed']+=1
                    family_value=r.get('family')
                    if isinstance(family_value,str) and family_value.startswith('['):
                        flattened=labels([family_value])
                        if flattened!=[family_value]:
                            r['family']=' + '.join(flattened)
                            repairs.append(dict(split=split,line=n,id=r['id'],field='family',before=family_value,after=r['family'],matching='serialization_only'))
                            counts['family_display_changed']+=1
                # No program, prompt, reward reference, static data, or identity changes.
                assert {k:v for k,v in r.items() if k not in ('db_meta','family')}=={k:v for k,v in original.items() if k not in ('db_meta','family')}
                handle.write(json.dumps(r,ensure_ascii=False)+'\n')
        files[split]=dict(rows=len(rows),sha256=sha(out/f'{split}.jsonl'),parent_sha256=sha(source/f'{split}.jsonl'))
    for name in ('row_manifest.jsonl','excluded_quarantine.jsonl','cross_stage_exposure.json','build_stats.json','static_dim_repairs.jsonl'):
        (out/name).write_bytes((source/name).read_bytes())
    for name,records in [('db_meta_repairs.jsonl',repairs),('db_meta_review_queue.jsonl',queue)]:
        (out/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    receipt=dict(status='PASS',parent='clean_v2',files=files,counts=dict(counts),
        db_snapshot_sha256=sha(AUDIT/'database_after.jsonl'),only_metadata_changed=True,
        script_sha256=sha(Path(__file__)),
        limits='127 unmatched body records and any nuclei disagreements remain in review; no heuristic matching. GRPO split isolation does not erase previous-stage exposure.')
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
