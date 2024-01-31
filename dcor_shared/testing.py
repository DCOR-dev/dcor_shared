from io import BytesIO

import ckan.tests.helpers as helpers
from ckan.tests.pytest_ckan.fixtures import FakeFileStorage
import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

import pytest


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


def make_dataset(create_context, owner_org, create_with_upload=None,
                 activate=False, **kwargs):
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
        rs = make_resource(create_with_upload, create_context, ds["id"])

    if activate:
        helpers.call_action("package_patch", create_context,
                            id=ds["id"],
                            state="active")

    ds_dict = helpers.call_action("package_show", id=ds["id"])

    if create_with_upload is not None:
        # updated resource dictionary
        rs_dict = helpers.call_action("resource_show", id=rs["id"])
        return ds_dict, rs_dict
    else:
        return ds_dict


def make_resource(resource_path, create_with_upload, create_context,
                  dataset_id):
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


def upload_presigned_to_s3(psurl, fields, path_to_upload):
    """Helper function for uploading data to S3

    This is exactly how DCOR-Aid would be uploading things (with the
    requests_toolbelt package). This could have been a little simpler,
    but for the sake of reproducibility, we do it the DCOR-Aid way.
    """
    # callback function for monitoring the upload progress
    # open the input file for streaming
    with path_to_upload.open("rb") as fd:
        fields["file"] = (fields["key"], fd)
        e = MultipartEncoder(fields=fields)
        m = MultipartEncoderMonitor(
            e, lambda monitor: print(f"Bytes: {monitor.bytes_read}"))
        # Increase the read size to speed-up upload (the default chunk
        # size for uploads in urllib is 8k which results in a lot of
        # Python code being involved in uploading a 20GB file; Setting
        # the chunk size to 4MB should increase the upload speed):
        # https://github.com/requests/toolbelt/issues/75
        # #issuecomment-237189952
        m._read = m.read
        m.read = lambda size: m._read(4 * 1024 * 1024)
        # perform the actual upload
        hrep = requests.post(
            psurl,
            data=m,
            headers={'Content-Type': m.content_type},
            verify=True,  # verify SSL connection
            timeout=27.3,  # timeout to avoid freezing
        )
    if hrep.status_code != 204:
        raise ValueError(
            f"Upload failed with {hrep.status_code}: {hrep.reason}")
