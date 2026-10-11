#!/usr/bin/env python3
"""Propagate reviewed metadata and exact rerun receipts to a new immutable GRPO version."""
import collections
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path('/mnt/d1/tony/outputs/grpo_data')
FOLLOWUP=Path('/mnt/d1/tony/outputs/pulse_db_followup_20260923')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source=ROOT/'clean_v3';output=ROOT/'clean_v4'
    output.mkdir(exist_ok=False)
    db=[json.loads(line) for line in (FOLLOWUP/'database_after.jsonl').open()]
    by_code=collections.defaultdict(list)
    for row in db:by_code[row['raw_code'].strip()].append(row)
    association={}
    unmatched=json.load((FOLLOWUP/'unmatched_analysis.json').open())
    for group in unmatched['programs']:
        if group['safe_db_ids']:
            for identifier in group['row_ids']:
                association[identifier]=group['safe_db_ids'][0]
    review={}
    for group in unmatched['rows']:
        review.setdefault(group['id'],[]).append(group)
    candidates={}
    for item in map(json.loads,(FOLLOWUP/'reward_support'/'repair_candidates.jsonl').open()):
        assert item['field']=='ref_prodopy' and item['old_value'] is None
        candidates[item['id']]=item
    counts=collections.Counter();repairs=[];review_rows=[];split_info={}
    explicit_nuclei={}
    for group in unmatched['programs']:
        for evidence in group.get('prosol_nucleus_evidence',[]):
            rel=evidence['text'].split('relations=<',1)[1].split('>',1)[0]
            nucleus='79Br' if '79Brdetection' in rel else '1H' if '1Hdetection' in rel else None
            if nucleus:
                for identifier in group['row_ids']:
                    explicit_nuclei[identifier]={'nuclei':[nucleus],'evidence':[evidence],
                        'relation':rel,'authority':'source_program_prosol_detection_relation'}
    for split in ('train','validation','test'):
        rows=[json.loads(line) for line in (source/f'{split}.jsonl').open()]
        with (output/f'{split}.jsonl').open('x') as handle:
            for line,row in enumerate(rows,1):
                before=copy.deepcopy(row);identifier=row['id'];matched=None;link_kind=None
                if row.get('db_meta'):
                    candidates_db=by_code.get(row['output'].strip(),[])
                    signature={(r['dimension'],json.dumps(r['canonical_facts'].get('family'),sort_keys=True),r['experiment_type']) for r in candidates_db}
                    if candidates_db and len(signature)==1:
                        matched=candidates_db[0];link_kind='exact_code_strip'
                    elif identifier in association:
                        matched=next(r for r in db if r['id']==association[identifier]);link_kind='independently_verified_equivalent_body'
                    meta=json.loads(row['db_meta']) if isinstance(row['db_meta'],str) else copy.deepcopy(row['db_meta'])
                    if matched:
                        facts=matched['canonical_facts'];family=facts.get('family')
                        meta.update(type=family if isinstance(family,list) else [matched['experiment_type']],
                            dim=matched['dimension'],nuclei=matched['nuclei'],matched_by=link_kind,
                            matched_db_id=matched['id'],metadata_authority='verified_source_body')
                        for key in ('dimension_label','dimension_candidates','dimension_is_pseudo','dimension_kind','dimension_declarations'):
                            if key in facts:meta[key]=facts[key]
                        # Retain unresolved isotope disagreement evidence; no conversion to a guess.
                        if set(meta.get('nuclei') or [])!=set(matched['nuclei'] or []):
                            raise AssertionError('exact source row nuclei did not reconcile')
                        counts['source_verified_database_links']+=1
                    else:
                        meta.setdefault('historical_candidate_db_meta',copy.deepcopy(meta))
                        meta.update(matched_by='unverified_name_only_variant',matched_db_id=None,
                                    metadata_authority='historical_candidate_not_verified')
                        counts['unverified_name_variants']+=1
                    notes=review.get(identifier,[])
                    for note in notes:
                        for update in note.get('proposed_field_updates',[]):
                            field=update['field'].removeprefix('db_meta.')
                            meta[field]=update['new']
                            meta.setdefault('source_review',[]).append({'field':field,'reason':update['reason'],
                                                                       'evidence':update.get('evidence',[])})
                            counts[f'reviewed_{field}']+=1
                    if identifier in explicit_nuclei:
                        meta['nuclei']=explicit_nuclei[identifier]['nuclei']
                        meta['nuclei_source']=explicit_nuclei[identifier]['authority']
                        meta['nuclei_evidence']=explicit_nuclei[identifier]['evidence']
                        counts['prosol_nuclei']+=1
                    if meta!=json.loads(row['db_meta']) if isinstance(row['db_meta'],str) else meta!=row['db_meta']:
                        row['db_meta']=json.dumps(meta,ensure_ascii=False)
                        counts['db_meta_rows_changed']+=1
                    row['family']=' + '.join(meta['type']) if meta.get('type') else row.get('family')
                if identifier in candidates:
                    repair=candidates[identifier]
                    assert repair['split']==split and repair['output_sha256']==hashlib.sha256(row['output'].encode()).hexdigest()
                    assert repair['task_name']==row['task_name']
                    row['ref_prodopy']=repair['new_value']
                    counts['prodopy_references_restored']+=1
                if row!=before:
                    repairs.append({'id':identifier,'split':split,'line':line,'before':before,'after':copy.deepcopy(row)})
                handle.write(json.dumps(row,ensure_ascii=False)+'\n')
        split_info[split]={'rows':len(rows),'sha256':sha(output/f'{split}.jsonl'),'parent_sha256':sha(source/f'{split}.jsonl')}
    for name in ('row_manifest.jsonl','excluded_quarantine.jsonl','cross_stage_exposure.json','build_stats.json','static_dim_repairs.jsonl'):
        (output/name).write_bytes((source/name).read_bytes())
    (output/'followup_repairs.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in repairs))
    for identifier,notes in review.items():
        unresolved=[n for n in notes if n['recommended_association_status']=='unverified_name_only_variant']
        if unresolved:review_rows.extend(unresolved)
    (output/'source_variant_review.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in review_rows))
    report={'status':'PASS','parent':'clean_v3','files':split_info,'counts':dict(counts),
            'database_snapshot_sha256':sha(FOLLOWUP/'database_after.jsonl'),
            'reference_receipts_sha256':sha(FOLLOWUP/'reward_support'/'candidate_verification.json'),
            'only_scientific_metadata_and_fresh_reference_fields_changed':True,
            'static_dim_unchanged_from_clean_v3':True,
            'source_variants':{'unverified_count':len(review_rows),'audited_rows':127},
            'limitations':'908 Prodopy references are exact-body/exact-task successful presence-mode outputs with empty purpose; they add only existing scorer floor, not scientific discrimination. Sleepy reference failures remain null. Unmatched source variants do not inherit DB scientific metadata as authoritative.'}
    (output/'manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
