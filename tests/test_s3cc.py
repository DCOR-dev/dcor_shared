import pathlib
import shutil
import time
from unittest import mock

import pytest

from ckan import model
import ckan.tests.helpers as helpers
import ckan.tests.factories as factories

from dcor_shared.testing import (
    make_dataset_via_s3, synchronous_enqueue_job, upload_presigned_to_s3
)
from dcor_shared import s3, s3cc, sha256sum

import h5py
import requests


data_path = pathlib.Path(__file__).parent / "data"


def setup_s3_resource_on_ckan(private: bool = False,
                              resource_path: str | pathlib.Path = None
                              ):
    """Create an S3 resource in CKAN"""
    if resource_path is None:
        resource_path = data_path / "calibration_beads_47.rtdc"

    file_size = resource_path.stat().st_size

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])

    test_context = {'ignore_auth': False,
                    'user': user['name'],
                    'model': model,
                    'api_version': 3}

    # Upload the resource to S3 (note that it is not required that the
    # dataset exists)
    response = helpers.call_action("resource_upload_s3_urls",
                                   test_context,
                                   organization_id=owner_org["id"],
                                   file_size=file_size,
                                   )
    rid = response["resource_id"]

    upload_presigned_to_s3(
        path=resource_path,
        upload_urls=response["upload_urls"],
        complete_url=response["complete_url"],
    )

    # Create the dataset
    pkg_dict = helpers.call_action("package_create",
                                   test_context,
                                   title="My Test Dataset",
                                   authors="Peter Parker",
                                   license_id="CC-BY-4.0",
                                   state="draft",
                                   private=private,
                                   owner_org=owner_org["name"],
                                   )

    # Update the dataset, creating the resource
    new_pkg_dict = helpers.call_action(
        "package_revise",
        test_context,
        match__id=pkg_dict["id"],
        update__resources__extend=[{"id": rid,
                                    "name": "new_test.rtdc",
                                    "s3_available": True,
                                    }],
        )
    assert new_pkg_dict["package"]["num_resources"] == 1
    s3_url = response["upload_urls"][0].split("?")[0]
    return rid, s3_url, new_pkg_dict, owner_org


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_artifact_exists(enqueue_job_mock):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan(private=True)
    assert s3cc.artifact_exists(rid)
    # Delete the object
    s3_client, _, _ = s3.get_s3()
    bucket_name, object_name = s3cc.get_s3_bucket_object_for_artifact(rid)
    s3_client.delete_object(
        Bucket=bucket_name,
        Key=object_name
    )
    assert not s3cc.artifact_exists(rid)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_compute_checksum(enqueue_job_mock):
    rid, _, _, _ = setup_s3_resource_on_ckan()
    assert s3cc.compute_checksum(rid) == \
           "490efdf5d9bb4cd4b2a6bcf2fe54d4dc201c38530140bcb168980bf8bf846c73"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_presigned_url(enqueue_job_mock, tmp_path):
    rid, _, _, _ = setup_s3_resource_on_ckan(private=True)
    psurl = s3cc.create_presigned_url(rid)
    response = requests.get(psurl)
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == \
        "490efdf5d9bb4cd4b2a6bcf2fe54d4dc201c38530140bcb168980bf8bf846c73"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_presigned_url_expires_at(enqueue_job_mock, tmp_path):
    rid, _, _, _ = setup_s3_resource_on_ckan(private=True)
    psurl, expires_at = s3cc.create_presigned_url(rid,
                                                  ret_expiration=True,
                                                  expiration=3600)
    time_created = time.time()
    response = requests.get(psurl)
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == \
        "490efdf5d9bb4cd4b2a6bcf2fe54d4dc201c38530140bcb168980bf8bf846c73"
    assert expires_at > time_created + 3000


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_attributes_for_artifact(enqueue_job_mock):
    rid, _, _, org_dict = setup_s3_resource_on_ckan()

    # Make sure the resource exists
    res_dict = helpers.call_action("resource_show", id=rid)
    assert res_dict["id"] == rid, "sanity check"

    # get the size
    meta = s3cc.get_s3_attributes_for_artifact(rid)
    assert meta["size"] == 904729
    assert meta["success"]
    assert meta["etag"]
    assert meta["server"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.ckan_config('dcor_object_store.bucket_name',
                         'circle-{organization_id}')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_bucket_object_for_artifact(enqueue_job_mock):
    rid, _, _, org_dict = setup_s3_resource_on_ckan()

    # Make sure the resource exists
    res_dict = helpers.call_action("resource_show", id=rid)
    assert res_dict["id"] == rid, "sanity check"

    # Compute the resource URL
    bucket_name, object_name = s3cc.get_s3_bucket_object_for_artifact(rid)
    assert bucket_name == f"circle-{org_dict['id']}"
    assert object_name == f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_handle(enqueue_job_mock):
    rid, _, _, _ = setup_s3_resource_on_ckan()
    with s3cc.get_s3_dc_handle(rid) as ds:
        assert len(ds) == 47


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_handle_condensed(enqueue_job_mock, tmp_path):
    resource_path = tmp_path / "data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", resource_path)
    _, res_dict = make_dataset_via_s3(
        resource_path=resource_path,
        activate=True)
    rid = res_dict["id"]
    expected_path = s3cc.get_s3_url_for_artifact(rid, artifact="condensed")
    with s3cc.get_s3_dc_handle(rid, artifact="condensed") as ds:
        assert ds.path == expected_path
        assert len(ds) == 47


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_dc_handle_basin_based(enqueue_job_mock, tmp_path):
    resource_path = tmp_path / "data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", resource_path)
    with h5py.File(resource_path, "a") as h5:
        del h5["events/volume"]

    _, res_dict = make_dataset_via_s3(
        resource_path=resource_path,
        activate=True)
    rid = res_dict["id"]

    # sanity check with reference
    with s3cc.get_s3_dc_handle(rid) as ds:
        assert "volume" not in ds.features_innate
        assert "image" in ds

    # actual test, the condensed dataset containing "volume" should be
    # in one of the basins.
    with s3cc.get_s3_dc_handle_basin_based(rid) as ds2:
        assert len(ds2.basins) == 2
        assert "volume" in ds2
        assert "volume" in ds2.features_basin
        assert "volume" not in ds2.features_innate
        assert "image" in ds2
        assert len(ds2) == 47


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_dc_handle_basin_based_public_urls(enqueue_job_mock, tmp_path):
    resource_path = tmp_path / "data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", resource_path)
    with h5py.File(resource_path, "a") as h5:
        del h5["events/volume"]

    _, res_dict = make_dataset_via_s3(
        resource_path=resource_path,
        private=False,
        activate=True)
    rid = res_dict["id"]

    with s3cc.get_s3_dc_handle_basin_based(rid) as ds:
        # get the basins
        for bn_dict in ds.basins_get_dicts():
            assert not bn_dict["perishable"]
            for url in bn_dict["urls"]:
                assert not url.lower().count("expires")


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_dc_handle_basin_based_private_urls(enqueue_job_mock, tmp_path):
    resource_path = tmp_path / "data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", resource_path)
    with h5py.File(resource_path, "a") as h5:
        del h5["events/volume"]

    _, res_dict = make_dataset_via_s3(
        resource_path=resource_path,
        private=True,
        activate=True)
    rid = res_dict["id"]

    with s3cc.get_s3_dc_handle_basin_based(rid) as ds:
        # get the basins
        for bn_dict in ds.basins_get_dicts():
            assert bn_dict["perishable"]
            for url in bn_dict["urls"]:
                assert url.lower().count("expires")


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_s3_url_for_artifact(enqueue_job_mock):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan()

    # Make sure the resource exists
    res_dict = helpers.call_action("resource_show", id=rid)
    assert res_dict["id"] == rid, "sanity check"

    # Compute the resource URL
    s3_url_exp = s3cc.get_s3_url_for_artifact(rid, artifact="resource")
    assert s3_url == s3_url_exp


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_make_resource_public(enqueue_job_mock):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan(private=True)
    resp1 = requests.get(s3_url)
    assert not resp1.ok, "sanity check"

    s3cc.make_resource_public(rid)
    resp2 = requests.get(s3_url)
    assert resp2.ok


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_artifact(enqueue_job_mock, tmp_path):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan(private=True)
    path_fake_preview = tmp_path / "test_preview.jpg"
    path_fake_preview.write_text("This is not a real image!")
    # upload the preview
    s3_url2 = s3cc.upload_artifact(rid,
                                   path_artifact=path_fake_preview,
                                   artifact="preview")
    assert s3_url == s3_url2.replace("preview", "resource")
    # make sure that worked
    assert s3cc.artifact_exists(rid, "preview")
    # attempt to download the private artifact
    resp1 = requests.get(s3_url.replace("resource", "preview"))
    assert not resp1.ok, "sanity check"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_artifact_public(enqueue_job_mock, tmp_path):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan(private=True)
    path_fake_preview = tmp_path / "test_preview.jpg"
    path_fake_preview.write_text("This is not a real image!")
    # upload the preview
    s3cc.upload_artifact(rid,
                         path_artifact=path_fake_preview,
                         artifact="preview",
                         # force public resource even though dataset is not
                         # (this has no real-life use case)
                         private=False)
    # make sure that worked
    assert s3cc.artifact_exists(rid, "preview")
    # attempt to download the private artifact
    resp1 = requests.get(s3_url.replace("resource", "preview"))
    assert resp1.ok, "preview should be public"
