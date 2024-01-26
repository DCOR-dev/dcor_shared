import base64
import hashlib
from unittest import mock
import pathlib
import uuid

import botocore.exceptions
import pytest
import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

from dcor_shared import s3, sha256sum


data_path = pathlib.Path(__file__).parent / "data"


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


def test_compute_checksum():
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)

    hash_exp = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_act = s3.compute_checksum(bucket_name=bucket_name,
                                   object_name=object_name)
    assert hash_exp == hash_act


def test_create_bucket_again():
    bucket_name = f"test-circle-{uuid.uuid4()}"
    bucket = s3.require_bucket(bucket_name)
    # this is cached
    bucket2 = s3.require_bucket(bucket_name)
    assert bucket2 is bucket, "cached"
    s3.require_bucket.cache_clear()
    bucket3 = s3.require_bucket(bucket_name)
    assert bucket3 is not bucket, "new object"


def test_make_object_public(tmp_path):
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)
    # Make sure object is not available publicly
    response = requests.get(s3_url)
    assert not response.ok, "resource is private"
    assert response.status_code == 403, "resource is private"
    # Make the object publicly accessible
    s3.make_object_public(bucket_name=bucket_name,
                          object_name=object_name)
    # Make sure the object is now publicly available
    response2 = requests.get(s3_url)
    assert response2.ok, "the resource is public, download should work"
    assert response2.status_code == 200, "download public resource"
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response2.content)
    assert sha256sum(dl_path) == sha256sum(path)


def test_make_object_public_no_such_key(tmp_path):
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)
    # Make sure object is not available publicly
    response = requests.get(s3_url)
    assert not response.ok, "resource is private"
    assert response.status_code == 403, "resource is private"
    # Try to make a non-existent object publicly accessible, no errors
    bad_object_name = object_name + "a"
    s3.make_object_public(bucket_name=bucket_name,
                          object_name=bad_object_name,
                          missing_ok=True)
    s3_client, _, _ = s3.get_s3()
    with pytest.raises(s3_client.exceptions.NoSuchKey):
        s3.make_object_public(bucket_name=bucket_name,
                              object_name=bad_object_name,
                              missing_ok=False)


def test_object_exists():
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)

    assert s3.object_exists(bucket_name=bucket_name,
                            object_name=object_name)
    # sanity checks
    assert not s3.object_exists(bucket_name=bucket_name,
                                object_name=f"peter/pan-{uuid.uuid4()}")
    assert not s3.object_exists(bucket_name=f"hansgunter-{uuid.uuid4()}",
                                object_name=object_name)


def test_presigned_url(tmp_path):
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)
    # Make sure object is not available publicly
    response = requests.get(s3_url)
    assert not response.ok, "resource is private"
    # Create a presigned URL
    ps_url = s3.create_presigned_url(bucket_name=bucket_name,
                                     object_name=object_name)
    response2 = requests.get(ps_url)
    assert response2.ok, "the resource is shared, download should work"
    assert response2.status_code == 200, "download public resource"
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response2.content)
    assert sha256sum(dl_path) == sha256sum(path)


@mock.patch(
    "dcor_shared.s3.create_time",
    new=iter([100, 100, 100,  # url0, url1, url2
              100, 102, 104,
              105, 109, 112,
              116, 117, 120]).__next__)
def test_presigned_url_caching():
    kwargs = {"bucket_name": "peterpan",
              "object_name": "object/a",
              }
    urls0 = [s3.create_presigned_url_until(bucket_name="peterpan",
                                           object_name="object/a",
                                           expires_at=150,
                                           filename=None)]
    urls1 = [s3.create_presigned_url_until(bucket_name="peterpan",
                                           object_name="object/a",
                                           expires_at=160,
                                           filename=None)]
    urls2 = [s3.create_presigned_url_until(bucket_name="peterpan",
                                           object_name="object/a",
                                           expires_at=170,
                                           filename=None)]
    for _ in range(3):
        urls0.append(s3.create_presigned_url(expiration=50, **kwargs))
    assert len(set(urls0)) == 1

    for _ in range(3):
        urls1.append(s3.create_presigned_url(expiration=50, **kwargs))
    assert len(set(urls1)) == 1

    for _ in range(3):
        urls2.append(s3.create_presigned_url(expiration=50, **kwargs))
    assert len(set(urls2)) == 1


def test_presigned_upload():
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    psurl, fields = s3.create_presigned_upload_url(bucket_name=bucket_name,
                                                   object_name=object_name)

    # This is what DCOR-Aid would do to upload the file
    upload_presigned_to_s3(psurl=psurl,
                           fields=fields,
                           path_to_upload=path
                           )

    hash_exp = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_act = s3.compute_checksum(bucket_name=bucket_name,
                                   object_name=object_name)
    assert hash_exp == hash_act


def test_presigned_upload_wrong_access():
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    psurl, fields = s3.create_presigned_upload_url(bucket_name=bucket_name,
                                                   object_name=object_name)
    # Try to upload the file under a different object name
    # (this tests the S3 access restrictions)
    rid2 = str(uuid.uuid4())
    object_name_bad = f"resource/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    # replace the old with the bad object name
    new_policy = base64.b64encode(
        base64.b64decode(fields["policy"])
        .decode("utf-8")
        .replace(object_name, object_name_bad)
        .encode("utf-8")
    )
    # sanity check
    assert new_policy != fields["policy"]
    fields["policy"] = new_policy
    fields["key"] = object_name_bad

    with pytest.raises(ValueError, match="Upload failed with 403: Forbidden"):
        # This is what DCOR-Aid would do to upload the file
        upload_presigned_to_s3(psurl=psurl,
                               fields=fields,
                               path_to_upload=path
                               )

    with pytest.raises(botocore.exceptions.ClientError, match="Not Found"):
        # Make sure the file does not exist
        s3.compute_checksum(bucket_name=bucket_name,
                            object_name=object_name_bad)


def test_presigned_upload_wrong_key():
    """Same as `test_presigned_upload_wrong_access` but no policy change"""
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    psurl, fields = s3.create_presigned_upload_url(bucket_name=bucket_name,
                                                   object_name=object_name)
    # Try to upload the file under a different object name
    # (this tests the S3 access restrictions)
    rid2 = str(uuid.uuid4())
    object_name_bad = f"resource/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    fields["key"] = object_name_bad

    with pytest.raises(ValueError, match="Upload failed with 403: Forbidden"):
        # This is what DCOR-Aid would do to upload the file
        upload_presigned_to_s3(psurl=psurl,
                               fields=fields,
                               path_to_upload=path
                               )

    with pytest.raises(botocore.exceptions.ClientError, match="Not Found"):
        # Make sure the file does not exist
        s3.compute_checksum(bucket_name=bucket_name,
                            object_name=object_name_bad)


def test_upload_override(tmp_path):
    path1 = tmp_path / "file1.rtdc"
    path2 = tmp_path / "file2.rtdc"
    with path1.open("wb") as fd:
        for ii in range(100):
            fd.write(b"0123456789")
    with path2.open("wb") as fd:
        for ii in range(50):
            fd.write(b"0123456789")
    # sanity check
    assert sha256sum(path1) != sha256sum(path2)
    # Proceed as in the other tests
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    # Original file
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path1,
        sha256=sha256sum(path1),
        private=False,
        override=False
    )
    response = requests.get(s3_url)
    dl_path = tmp_path / "test1.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == sha256sum(path1)

    # New file without override
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path2,
        sha256=sha256sum(path2),
        private=False,
        override=False,
    )
    response = requests.get(s3_url)
    dl_path = tmp_path / "test1.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == sha256sum(path1)

    # New file with override
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path2,
        sha256=sha256sum(path2),
        private=False,
        override=True,
    )
    response = requests.get(s3_url)
    dl_path = tmp_path / "test2.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == sha256sum(path2)


def test_upload_large_file(tmp_path):
    # Create a ~100MB file
    path = tmp_path / "large_file.rtdc"
    with path.open("wb") as fd:
        for ii in range(100):
            fd.write(b"0123456789"*100000)
    # Proceed as in the other tests
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=False)
    # Make sure object is available publicly
    response = requests.get(s3_url)
    assert response.ok, "the resource is public, download should work"
    assert response.status_code == 200, "download public resource"
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == sha256sum(path)


def test_upload_private(tmp_path):
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=True)
    # Make sure object is not available publicly
    response = requests.get(s3_url)
    assert not response.ok, "resource is private"
    assert response.status_code == 403, "resource is private"


def test_upload_public(tmp_path):
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=object_name,
        path=path,
        sha256=sha256sum(path),
        private=False)
    # Make sure object is available publicly
    response = requests.get(s3_url)
    assert response.ok, "the resource is public, download should work"
    assert response.status_code == 200, "download public resource"
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    assert sha256sum(dl_path) == sha256sum(path)


def test_upload_wrong_sha256():
    path = data_path / "calibration_beads_47.rtdc"
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        s3.upload_file(
            bucket_name=bucket_name,
            object_name=object_name,
            path=path,
            sha256="INCORRECT-CHECKSUM",
            private=False)
