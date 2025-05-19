from __future__ import annotations

from io import BytesIO
import numbers
import pathlib
from typing import Dict, List
import uuid
import warnings

import ckan.authz
import ckan.model
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
from ckan.tests.pytest_ckan.fixtures import FakeFileStorage
import requests

import pytest

from .ckan import get_ckan_config_option
from . import s3


@pytest.fixture
def create_with_upload_no_temp(clean_db, ckan_config, monkeypatch):
    """
    Create upload without tempdir
    """

    def factory(data, filename, context=None, **kwargs):
        if context is None:
            context = {}
        action = kwargs.pop("action", "resource_create")
        field = kwargs.pop("upload_field_name", "upload")
        test_file = BytesIO()
        if type(data) is not bytes:
            data = bytes(data, encoding="utf-8")
        test_file.write(data)
        test_file.seek(0)
        test_resource = FakeFileStorage(test_file, filename)

        params = {
            field: test_resource,
        }
        params.update(kwargs)
        return helpers.call_action(action, context, **params)
    return factory


def make_dataset(create_context=None, owner_org=None, create_with_upload=None,
                 resource_path=None, activate=False, **kwargs):
    """Create a dataset with a resource for testing"""
    warnings.warn(
        "`make_dataset` is deprecated, use `make_dataset_via_s3` instead",
        DeprecationWarning)

    if create_context is None:
        user = factories.User()
        create_context = {'ignore_auth': False,
                          'user': user['name'],
                          'api_version': 3}
        user_id = user["id"]
    else:
        # get user ID from create_context
        user_id = ckan.authz.get_user_id_for_username(
            create_context["user"], allow_none=True)

    if owner_org is None:
        owner_org = factories.Organization(users=[{
            'name': user_id,
            'capacity': 'admin'
        }])

    if "title" not in kwargs:
        kwargs["title"] = "test-dataset"
    if "authors" not in kwargs:
        kwargs["authors"] = "Peter Pan"
    if "license_id" not in kwargs:
        kwargs["license_id"] = "CC-BY-4.0"
    assert "state" not in kwargs, "must not be set"
    assert "owner_org" not in kwargs, "must not be set"
    # create a dataset
    ds = helpers.call_action("package_create", create_context,
                             owner_org=owner_org["name"],
                             state="draft",
                             **kwargs
                             )

    if create_with_upload is not None:
        rs = make_resource(resource_path=resource_path,
                           create_with_upload=create_with_upload,
                           create_context=create_context,
                           dataset_id=ds["id"])

    if activate:
        revise_dict = {
            "match": {"id": ds["id"]},
            "update": {"state": "active"}
        }
        helpers.call_action("package_revise", create_context, **revise_dict)

    ds_dict = helpers.call_action("package_show", id=ds["id"])

    if create_with_upload is not None:
        # updated resource dictionary
        rs_dict = helpers.call_action("resource_show", id=rs["id"])
        return ds_dict, rs_dict
    else:
        return ds_dict


def make_dataset_via_s3(
        create_context: Dict | None = None,
        owner_org: Dict | None = None,
        resource_path: str | pathlib.Path | None = None,
        activate: bool = False,
        **kwargs: str | numbers.Number):
    """Create a dataset and upload the given resource directly via S3

    For this action to work, the "ckanext-dcor_schemas" extension
    must be loaded.

    Parameters
    ----------
    create_context: dict
        CKAN context for creating the dataset
    owner_org: dict
        CKAN dictionary of the owner organization
    resource_path: str or pathlib.Path
        path to the resource file to upload. If not specified, then
        no resource is created for the dataset
    activate: bool
        whether to activate the dataset
    kwargs: dict
        keyword arguments passed to `package_create`
    """
    if create_context is None:
        user = factories.User()
        user_obj = ckan.model.User.by_name(user["name"])
        create_context = {'ignore_auth': False,
                          'auth_user_obj': user_obj,
                          'user': user['name'],
                          'api_version': 3}
        user_id = user["id"]
    else:
        # get user ID from create_context
        user_id = ckan.authz.get_user_id_for_username(
            create_context["user"], allow_none=True)

    if owner_org is None:
        owner_org = factories.Organization(
            users=[{
                'name': user_id,
                'capacity': 'admin'
            }])

    if "title" not in kwargs:
        kwargs["title"] = "test-dataset-S3"
    if "authors" not in kwargs:
        kwargs["authors"] = "Peter Fly Pan"
    if "license_id" not in kwargs:
        kwargs["license_id"] = "CC-BY-4.0"
    assert "state" not in kwargs, "must not be set"
    assert "owner_org" not in kwargs, "must not be set"
    # create a dataset
    ds_dict = helpers.call_action("package_create", create_context,
                                  owner_org=owner_org["name"],
                                  state="draft",
                                  **kwargs
                                  )

    if resource_path is not None:
        rid = make_resource_via_s3(resource_path=resource_path,
                                   organization_id=owner_org["id"],
                                   dataset_id=ds_dict["id"],
                                   private=ds_dict.get("private", False)
                                   )
    else:
        rid = None

    if activate:
        revise_dict = {
            "match": {"id": ds_dict["id"]},
            "update": {"state": "active"}
        }
        helpers.call_action("package_revise", create_context, **revise_dict)

    ds_dict = helpers.call_action("package_show", id=ds_dict["id"])

    if rid is not None:
        # fetch resource dictionary
        rs_dict = helpers.call_action("resource_show", id=rid)
        return ds_dict, rs_dict
    else:
        return ds_dict


def make_resource(resource_path, create_with_upload, create_context,
                  dataset_id):
    warnings.warn(
        "`make_resource` is deprecated, use `make_resource_via_s3` instead",
        DeprecationWarning)
    content = resource_path.read_bytes()
    rs = create_with_upload(
        data=content,
        filename='test.rtdc',
        context=create_context,
        package_id=dataset_id,
        url="upload",
    )
    resource = helpers.call_action("resource_show", id=rs["id"])
    return resource


def make_resource_via_s3(
        resource_path: pathlib.Path | str,
        organization_id: str,
        dataset_id: str,
        create_context: Dict = None,
        private: bool = False,
        ret_dict: bool = False,
        ):
    """Upload a resource to S3 and register it with CKAN"""
    if create_context is not None:
        warnings.warn("Create context has no effect for creating resources "
                      f"via S3 for testing (got {create_context})",
                      DeprecationWarning)

    user = factories.Sysadmin()
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=organization_id)
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    s3.upload_file(bucket_name=bucket_name,
                   object_name=object_name,
                   path=resource_path,
                   private=private)

    revise_dict = {
        "match": {"id": dataset_id},
        "update__resources__extend": [{
            "id": rid,
            "name": resource_path.name,
            "s3_available": True,
            }]
        }
    helpers.call_action("package_revise", create_context, **revise_dict)
    if ret_dict:
        res_dict = helpers.call_action("resource_show", id=rid)
        return res_dict
    else:
        return rid


def synchronous_enqueue_job(job_func, args=None, kwargs=None, title=None,
                            queue=None, rq_kwargs=None):
    """
    Synchronous mock for ``ckan.plugins.toolkit.enqueue_job``.

    Due to the asynchronous nature of background jobs, code that uses them
    needs to be handled specially when writing tests.

    A common approach is to use the mock package to replace the
    ckan.plugins.toolkit.enqueue_job function with a mock that executes jobs
    synchronously instead of asynchronously

    Also, since we are running the tests as root on a ckan instance that
    is run by www-data, modifying files on disk in background jobs
    (which were started by supervisor as www-data) does not work.
    """
    if rq_kwargs is None:
        rq_kwargs = {}
    args = args or []
    kwargs = kwargs or {}
    job_func(*args, **kwargs)


def upload_presigned_to_s3(
        path: str | pathlib.Path,
        upload_urls: List[str],
        complete_url: str | None):
    """Helper function for uploading data to S3

    This is how DCOR-Aid would be uploading things.

    Parameters
    ----------
    path: str or pathlib.Path
        file to upload
    upload_urls: list
        List of the presigned URLs required for the upload.
        There will always be the key "urls" containing a list of
        presigned URLs.
    complete_url: str
        If a multipart upload is necessary, this is the presigned URL
        required to finalize the upload. For more information, see
        `https://boto3.amazonaws.com/v1/documentation/api/latest/
        reference/services/s3/client/complete_multipart_upload.html
        #complete-multipart-upload`_ or the example below
    """
    path = pathlib.Path(path)
    with path.open("rb") as fd:
        if len(upload_urls) > 1:
            # Multipart upload
            # Determine the part size for multipart upload
            num_parts = len(upload_urls)
            file_size = path.stat().st_size
            if file_size % num_parts == 0:
                part_size = file_size // num_parts
            else:
                part_size = file_size // num_parts + 1
            # Upload each part
            etags = []
            for psurl in upload_urls:
                respi = requests.put(psurl,
                                     data=fd.read(part_size),
                                     timeout=3,
                                     )
                etag_part = respi.headers.get("ETag", "").strip("'").strip('"')
                etags.append(etag_part)
            # Finish the multipart upload
            c_xml = "<CompleteMultipartUpload>\n"
            for ii, etag in enumerate(etags):
                c_xml += ("  <Part>\n"
                          + f"    <PartNumber>{ii + 1}</PartNumber>\n"
                          + f"    <ETag>{etag}</ETag>\n"
                          + "  </Part>\n"
                          )
            c_xml += "</CompleteMultipartUpload>"
            resp = requests.post(
                complete_url,
                data=c_xml,
                timeout=3,
            )
            etag_full = resp.headers.get("ETag", "").strip("'").strip('"')
        else:
            # Single file upload
            resp = requests.put(upload_urls[0],
                                data=fd,
                                timeout=3)
            etag_full = resp.headers.get("ETag", "").strip("'").strip('"')
    if not etag_full:
        raise ValueError(
            f"Upload failed with {resp.status_code}: {resp.reason} "
            f"({resp.headers})")
    return etag_full
