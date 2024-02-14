import atexit
import pathlib
import shutil
from unittest import mock
import uuid

from ckan import logic
import ckanext.dcor_schemas.plugin

from dcor_shared import (
    get_dc_instance, get_resource_path, s3, sha256sum, wait_for_resource
)

import pytest
import ckan.tests.factories as factories
from dcor_shared.testing import make_dataset, synchronous_enqueue_job

data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_file(enqueue_job_mock, create_with_upload,
                              monkeypatch):
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    ds_dict, _ = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    rid = ds_dict["resources"][0]["id"]
    resource_path = pathlib.Path(get_resource_path(rid))
    assert resource_path.exists(), "sanity check"
    with get_dc_instance(rid) as ds:
        assert str(ds.path) == str(resource_path)


@pytest.mark.ckan_config('ckan.storage_path',
                         '/tmp/test_dcor_shared/test_get_dc_instance')
def test_get_dc_instance_file_fails_without_actual_resource():
    tmp_path = pathlib.Path("/tmp/test_dcor_shared/test_get_dc_instance")
    atexit.register(shutil.rmtree,
                    tmp_path,
                    ignore_errors=True)
    rid = str(uuid.uuid4())
    resource_path = tmp_path / rid[:3] / rid[3:6] / rid[6:]
    resource_path.parent.mkdir(parents=True)
    shutil.copy2(data_path / "calibration_beads_47.rtdc", resource_path)
    with pytest.raises(logic.NotFound):
        get_dc_instance(rid)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_s3(enqueue_job_mock, create_with_upload,
                            monkeypatch):
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    ds_dict, _ = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    res_dict = ds_dict["resources"][0]
    rid = res_dict["id"]
    resource_path = pathlib.Path(get_resource_path(rid))
    # remove the file, so DCOR falls back to the S3 resource
    resource_path.unlink()
    assert not resource_path.exists(), "sanity check"
    with get_dc_instance(rid) as ds:
        assert ds.path.startswith("http")
        assert res_dict["s3_available"]
        assert res_dict["s3_url"] == ds.path


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_s3_fails_without_actual_resource(enqueue_job_mock):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    rid = str(uuid.uuid4())
    bucket_name = f"circle-{owner_org['id']}"
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    upload_path = data_path / "calibration_beads_47.rtdc"
    s3.upload_file(bucket_name=bucket_name,
                   object_name=object_name,
                   path=upload_path,
                   sha256=sha256sum(upload_path)
                   )
    with pytest.raises(logic.NotFound):
        get_dc_instance(rid)


def test_sha256sum(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("Sum this up!")
    ist = sha256sum(p)
    soll = "d00df55b97a60c78bbb137540e1b60647a5e6b216262a95ab96cafd4519bcf6a"
    assert ist == soll


def test_wait_for_resource_s3(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id,
                            "s3_available": True})
    # Should not raise an exception
    wait_for_resource(res_id)


@pytest.mark.ckan_config('ckan.plugins', '')  # disable plugins
def test_wait_for_resource_no_s3_url_no_plugins(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Create the actual path
    rp = pathlib.Path(get_resource_path(res_id))
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_bytes(b"This is not a dummy file, but a fake DC file!")
    # Should not raise an exception
    wait_for_resource(res_id)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot')
def test_wait_for_resource_no_s3_url_with_dcor_depot_plugin(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Create the actual path
    rp = pathlib.Path(get_resource_path(res_id))
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_bytes(b"This is not a dummy file, but a fake DC file!")
    rp2 = rp.with_name("test.rtdc")
    rp.rename(rp2)
    rp.symlink_to(rp2)

    # Should not raise an exception
    wait_for_resource(res_id)


def test_wait_resource_not_available(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Should raise an exception
    with pytest.raises(OSError, match="Data import seems to take too long"):
        wait_for_resource(res_id, timeout=1)
