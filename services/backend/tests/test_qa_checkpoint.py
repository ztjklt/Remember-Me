"""Evaluation history must not become a mixed full/subset passing report."""
import importlib.util
from pathlib import Path
import pytest


def runner():
    path=Path(__file__).resolve().parents[3]/'tools/round_two/live_check.py'
    spec=importlib.util.spec_from_file_location('qa_live_runner',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_historical_checkpoint_cannot_be_reinterpreted_as_a_subset():
    report={'people':{'p':{'p-q01':{'error':'old failure'}}}}
    with pytest.raises(ValueError,match='scope'):
        runner().validate_checkpoint(report,['p-q02'],'cloud-monthly')


def test_saved_subset_and_dataset_are_immutable():
    report={'selected_cases':['p-q01'],'dataset':'cloud-monthly'}
    module=runner()
    module.validate_checkpoint(report,['p-q01'],'cloud-monthly')
    for selected,dataset in [([], 'cloud-monthly'),(['p-q01'],'legacy')]:
        with pytest.raises(ValueError):module.validate_checkpoint(report,selected,dataset)
