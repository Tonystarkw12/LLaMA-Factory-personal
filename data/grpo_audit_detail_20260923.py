#!/usr/bin/env python3
"""Source-bound cross-stage and reference-field GRPO audit; no dataset edits."""
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path('/mnt/d1/tony/outputs/grpo_data')
AUDIT = Path(__file__).resolve().parent / 'nmr_v3/quality_audit_20260923'


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def program(row):
    return row.get('output', row.get('chosen', '')).strip()


def triplet(row):
    return tuple(row[k].strip() for k in ('instruction', 'input', 'output'))


def pair(row):
    return tuple(row[k] for k in ('instruction', 'input', 'chosen', 'rejected'))


def main():
    files = {p.name: read(p) for p in sorted(ROOT.glob('*.jsonl'))}
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.jsonl')}
    result = dict(source_hashes=hashes, normalized_cross_checks=[], pair_checks={}, references={},
                  quarantined_sft_carryover={}, sft_cross_checks={}, candidates={})
    for name, rows in files.items():
        if 'chosen' in rows[0]:
            result['pair_checks'][name] = dict(rows=len(rows), duplicate_pair_excess=len(rows)-len({pair(r) for r in rows}),
                identical_chosen_rejected_lines=[i for i,r in enumerate(rows,1) if r['chosen']==r['rejected']])
    targets = [('grpo_train.jsonl', 'grpo_val.jsonl')]
    targets += [(train,test) for train in ('grpo_train.jsonl','rm_run3_train.jsonl','gate11_singles_train.jsonl')
                for test in ('gate10_singles_test.jsonl','gate10_doubles_test.jsonl')]
    for a,b in targets:
        outputs = {program(r) for r in files[a]}
        hits = [i for i,r in enumerate(files[b],1) if program(r) in outputs]
        hit = dict(reference_file=a, checked_file=b, checked_rows=len(files[b]), output_overlap_rows=len(hits),
                   checked_file_lines=hits, normalization='strip leading/trailing whitespace only')
        if 'chosen' in files[a][0] and 'chosen' in files[b][0]:
            pairs = {pair(r) for r in files[a]}
            hit['exact_pair_overlap_lines'] = [i for i,r in enumerate(files[b],1) if pair(r) in pairs]
        result['normalized_cross_checks'].append(hit)
    quarantine = {triplet(r['record']):r for r in read(AUDIT/'quarantine_final.jsonl')}
    for name in ('grpo_train.jsonl','grpo_val.jsonl'):
        rows = files[name]
        result['quarantined_sft_carryover'][name] = [dict(line=i,id=r['id'],
            original_source_line=quarantine[triplet(r)]['source_line'],
            reason=quarantine[triplet(r)]['reason']) for i,r in enumerate(rows,1) if triplet(r) in quarantine]
        refs = {}
        for field in ('static','ref_sleepy','ref_prodopy','ref_timeline','db_meta'):
            states=collections.Counter(); bad=[]
            for i,r in enumerate(rows,1):
                if not r.get(field):
                    states['empty_or_absent']+=1
                    continue
                try:
                    value=json.loads(r[field]);states[type(value).__name__]+=1
                except (ValueError,TypeError) as exc:
                    bad.append(dict(line=i,error=str(exc)))
            refs[field]=dict(states=dict(states),malformed=bad)
        refs['engine_support_false_lines']=[i for i,r in enumerate(rows,1) if not r['engine_support']]
        refs['engine_support_inconsistent_with_sleepy_lines']=[i for i,r in enumerate(rows,1)
                                                              if bool(r['ref_sleepy']) != r['engine_support']]
        result['references'][name]=refs
        result['candidates'][name]=dict(gradient_requested_but_static_has_no_gradient_lines=[
            i for i,r in enumerate(rows,1) if 'gradient-selection' in r['instruction'] and not json.loads(r['static'])['gradients']],
            note='Review queue only; static extraction is not a compiler and may miss macros/includes.')
        result['sft_cross_checks'][name]={}
        for split in ('train','validation','test'):
            sr=read(AUDIT/'split_6400_v1'/f'{split}.jsonl'); outputs={program(r) for r in sr}
            hits=[i for i,r in enumerate(rows,1) if program(r) in outputs]
            result['sft_cross_checks'][name][split]=dict(grpo_rows=len(hits),grpo_lines=hits)
    result['build_stats'] = json.loads((ROOT/'build_stats.json').read_text())
    result['current_rows'] = {name:len(rows) for name,rows in files.items()}
    result['source_unchanged'] = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in hashes.items())
    assert result['source_unchanged']
    (ROOT/'grpo_audit_details.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS: source files unchanged; wrote grpo_audit_details.json')


if __name__ == '__main__':
    main()
