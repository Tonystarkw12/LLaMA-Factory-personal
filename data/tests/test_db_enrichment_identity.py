import importlib.util
from pathlib import Path

PATH = Path('/mnt/d1/tony/outputs/nmr_rl/scripts/enrich_labels_from_db.py')
spec = importlib.util.spec_from_file_location('db_enrichment_identity', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(code, filename='same.pp'):
    return {'id': 1, 'filename': filename, 'raw_code': code, 'experiment_type': 'HSQC + COSY',
            'experiment_subtype': None, 'dimension': 2, 'nuclei': ['1H'],
            'canonical_facts': {'family': ['HSQC', 'COSY']}}


def test_same_name_different_body_does_not_import_labels():
    rec = {'output': ';same\n1 ze\nexit', 'task_name': 'zg', 'family': 'OLD'}
    before = rec.copy()
    assert not module.label_from_meta(rec, {'same': row(';same\n1 ze\ngo=2 ph31')})
    assert rec == before


def test_same_body_matches_despite_wrong_first_line_name_and_keeps_reference_task():
    code = ';wrong_copied_name\n1 ze\nexit'
    rec = {'output': code, 'task_name': 'zg', 'ref_sleepy': '{"peaks":[]}', 'family': 'OLD'}
    assert module.label_from_meta(rec, {'same': row(code)})
    assert rec['db_meta']['type'] == ['HSQC', 'COSY']
    assert rec['db_meta']['matched_by'] == 'exact_code_strip'
    assert rec['db_meta']['matched_db_id'] == 1
    assert rec['task_name'] == 'zg'  # existing signatures are filename-sensitive


def test_ambiguous_same_body_scientific_metadata_is_not_selected():
    code = ';sample\n1 ze\nexit';one=row(code);two=row(code,'other.pp');two['dimension']=3
    assert not module.label_from_meta({'output': code}, {'one': one, 'two': two})
