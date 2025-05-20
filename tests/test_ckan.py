import pathlib
from unittest import mock

from dcor_shared import (
    get_resource_dc_config, get_resource_info, is_resource_private
)

import pytest
from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job

data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_resource_dc_config(enqueue_job_mock):
    _, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    dc_config = get_resource_dc_config(res_dict["id"])
    assert dc_config["experiment"]["event count"] == 47
    assert dc_config["experiment"]["date"] == "2018-12-11"
    assert dc_config["fluorescence"]["laser count"] == 2


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_resource_info(enqueue_job_mock):
    ds_dict, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    ds_dict_2, res_dict_2 = get_resource_info(res_dict["id"])
    assert ds_dict == ds_dict_2
    assert res_dict == res_dict_2


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@pytest.mark.parametrize("private", [True, False])
def test_is_resource_private(private):
    _, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        private=private,
        activate=True)
    assert is_resource_private(res_dict["id"]) == private
