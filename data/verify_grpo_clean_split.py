#!/usr/bin/env python3
"""Independently reopen and verify the exported GRPO data and exposure scope."""
import collections
import hashlib
import itertools
import json
import re
from pathlib import Path

ROOT = Path('/mnt/d1/tony/outputs/grpo_data')
OUT = ROOT/'clean_v1'
REPO = Path(__file__).resolve().parents[1]
SFT = REPO/'data/nmr_v3/quality_audit_20260923'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def fp(row):
    text = row.get('output',row.get('chosen','')).strip()
    body = '\n'.join(s.strip() for s in text.splitlines() if s.strip() and not s.lstrip().startswith(';'))
    first = text.splitlines()[0].lstrip(';').strip() if text else ''
    name = first.lower() if text.startswith(';') and re.fullmatch(r'[A-Za-z][\w.-]*',first) else ''
    prompt = '\n'.join((row.get('instruction',''),row.get('input','')))
    return dict(output=text,body=body,name=name,name_numeric_family=re.sub(r'(?:\.\d+)+$','',name),prompt=prompt)


def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    original={name:(ROOT/name).read_bytes().splitlines(keepends=True) for name in manifest['source_files']}
    for name,value in manifest['source_files'].items():
        assert digest(ROOT/name)==value
    quarantine=read(SFT/'quarantine_final.jsonl')
    q={tuple(r['record'][k] for k in ('instruction','input','output')) for r in quarantine}
    rows={split:read(OUT/f'{split}.jsonl') for split in ('train','validation','test')}
    lineage=read(OUT/'row_manifest.jsonl')
    excluded=read(OUT/'excluded_quarantine.jsonl')
    all_refs=set()
    for split,rs in rows.items():
        path=OUT/f'{split}.jsonl'
        refs=[r for r in lineage if r['split']==split]
        assert len(rs)==len(refs)==manifest['files'][split]['rows']
        assert digest(path)==manifest['files'][split]['sha256']
        expected=[]
        for row,ref in zip(rs,refs):
            source=ref['source'];key=(source['source_file'],source['source_line'])
            assert key not in all_refs
            all_refs.add(key)
            raw=original[key[0]][key[1]-1]
            assert json.loads(raw)==row and row['id']==ref['id']
            assert tuple(row[k] for k in ('instruction','input','output')) not in q
            expected.append(raw)
        assert path.read_bytes()==b''.join(expected)
    for item in excluded:
        source=item['source'];key=(source['source_file'],source['source_line'])
        assert key not in all_refs
        all_refs.add(key)
        row=json.loads(original[key[0]][key[1]-1])
        assert row['id']==item['id']
        assert tuple(row[k] for k in ('instruction','input','output')) in q
    assert len(excluded)==253
    assert all_refs=={(name,i) for name,lines in original.items() for i in range(1,len(lines)+1)}
    fps={k:[fp(r) for r in v] for k,v in rows.items()}
    overlaps={}
    for a,b in itertools.combinations(rows,2):
        overlaps[a+'_vs_'+b]={kind:len({f[kind] for f in fps[a] if f[kind]} & {f[kind] for f in fps[b] if f[kind]}) for kind in fps[a][0]}
        assert not any(overlaps[a+'_vs_'+b].values())
    # Detect excluded-row bridges by grouping ALL source records before deletion.
    source_rows=[json.loads(line) for lines in original.values() for line in lines]
    parents=list(range(len(source_rows)))
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    seen={}
    for i,r in enumerate(source_rows):
        for kind,value in fp(r).items():
            if not value:continue
            key=kind,value
            if key in seen:parents[find(i)]=find(seen[key])
            seen[key]=i
    assignment={r['id']:split for split,rs in rows.items() for r in rs}
    component_splits=collections.defaultdict(set)
    for i,r in enumerate(source_rows):
        if r['id'] in assignment:component_splits[find(i)].add(assignment[r['id']])
    bridge_conflicts=sum(len(s)>1 for s in component_splits.values())
    assert bridge_conflicts==0, 'Quarantined bridge splits a program component'
    # Metadata is preserved, but callers must not mistake it for validated physics.
    review=[]
    for split,rs in rows.items():
        for n,row in enumerate(rs,1):
            static=json.loads(row['static'])
            dim=re.search(r'^\s*;\$DIM\s*=\s*([^\s;]+)',row['output'],re.M)
            if dim and dim.group(1).upper()!=str(static.get('dim','')).upper():
                review.append(dict(split=split,line=n,id=row['id'],issue='static_dim_vs_header',
                                   static_dim=static.get('dim'),header_dim=dim.group(1)))
    (OUT/'metadata_review_queue.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in review))
    external={f'sft_{split}':SFT/'split_6400_v1'/f'{split}.jsonl' for split in ('train','validation','test')}
    external.update(dpo=REPO/'data/nmr_pulse_program_dpo_5120.jsonl',rm_train=ROOT/'rm_run3_train.jsonl',
                    gate10_singles=ROOT/'gate10_singles_test.jsonl',gate10_doubles=ROOT/'gate10_doubles_test.jsonl')
    exposure={}
    for name,path in external.items():
        ext=[fp(r) for r in read(path)]
        values={kind:{f[kind] for f in ext if f[kind]} for kind in ext[0]}
        exposure[name]=dict(source_sha256=digest(path),splits={})
        for split,fs in fps.items():
            hits={kind:[i for i,f in enumerate(fs,1) if f[kind] and f[kind] in keys] for kind,keys in values.items()}
            exposure[name]['splits'][split]=dict(any_overlap_rows=len(set(itertools.chain.from_iterable(hits.values()))),
                                                exact_output_rows=len(hits['output']),lines_by_fingerprint=hits)
    (OUT/'cross_stage_exposure.json').write_text(json.dumps(exposure,indent=2)+'\n')
    result=dict(status='PASS',all_source_lines_accounted=True,source_rows=len(source_rows),
        excluded_rows=len(excluded),retained_rows=sum(map(len,rows.values())),
        rows={k:len(v) for k,v in rows.items()},all_exported_lines_byte_identical=True,
        source_files_unchanged=True,cross_split_overlap=overlaps,excluded_bridge_conflicts=bridge_conflicts,
        static_dim_review_rows=len(review),script_sha256=digest(Path(__file__)),
        limitation='GRPO-internal split isolation only; prior-stage/model exposure remains. No training or reward execution.')
    (OUT/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
