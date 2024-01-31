import pathlib
from unittest import mock

import pytest

from ckan import model
import ckan.tests.helpers as helpers
import ckan.tests.factories as factories

from dcor_shared.testing import synchronous_enqueue_job, upload_presigned_to_s3
from dcor_shared import s3, s3cc, sha256sum

import requests


data_path = pathlib.Path(__file__).parent / "data"


def setup_s3_resource_on_ckan(private=False):
    """Create an S3 resource in CKAN"""
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])

    test_context = {'ignore_auth': False,
                    'user': user['name'], 'model': model, 'api_version': 3}

    # Upload the resource to S3 (note that it is not required that the
    # dataset exists)
    response = helpers.call_action("resource_upload_s3_url",
                                   test_context,
                                   organization_id=owner_org["id"],
                                   )
    rid = response["resource_id"]
    upload_presigned_to_s3(
        psurl=response["url"],
        fields=response["fields"],
        path_to_upload=data_path / "calibration_beads_47.rtdc")

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
    s3_url = response["url"] + "/" + response["fields"]["key"]
    return rid, s3_url, new_pkg_dict, owner_org


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
def test_object_exists(enqueue_job_mock):
    rid, s3_url, _, org_dict = setup_s3_resource_on_ckan(private=True)
    assert s3cc.object_exists(rid)
    # Delete the object
    s3_client, _, _ = s3.get_s3()
    bucket_name, object_name = s3cc.get_s3_bucket_object_for_artifact(rid)
    s3_client.delete_object(
        Bucket=bucket_name,
        Key=object_name
    )
    assert not s3cc.object_exists(rid)
