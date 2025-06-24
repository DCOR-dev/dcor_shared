import hashlib
from unittest import mock
import pathlib
import time
import uuid

import botocore.exceptions
import pytest
import requests

from dcor_shared import s3, sha256sum, get_ckan_config_option
from dcor_shared.testing import upload_presigned_to_s3


data_path = pathlib.Path(__file__).parent / "data"


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


def test_iter_bucket_objects():
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
    assert len(list(s3.iter_bucket_objects(bucket_name,
                                           older_than_days=0))) == 1
    assert len(list(s3.iter_bucket_objects(bucket_name,
                                           older_than_days=1))) == 0


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
    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        file_size=path.stat().st_size,
    )

    assert len(upload_urls) == 1, "no multipart upload"
    assert complete_url is None, "no multipart upload"

    # This is what DCOR-Aid would do to upload the file
    etag = upload_presigned_to_s3(
        path=path,
        upload_urls=upload_urls,
        complete_url=complete_url,
        )

    assert hashlib.md5(path.read_bytes()).hexdigest() == etag

    hash_exp = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_act = s3.compute_checksum(bucket_name=bucket_name,
                                   object_name=object_name)
    assert hash_exp == hash_act


def test_presigned_upload_multipart(tmp_path):
    path = tmp_path / "calibration_beads_47.rtdc"
    with path.open("wb") as fd:
        for ii in range(20):  # 20 MiB
            fd.write(bytearray(1024**2))

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        # pretend as if we had a huge file
        file_size=int(1.5*1024**3),
    )

    assert len(upload_urls) == 2, "multipart upload"
    assert complete_url is not None, "multipart upload"

    # This is what DCOR-Aid would do to upload the file
    etag = upload_presigned_to_s3(
        path=path,
        upload_urls=upload_urls,
        complete_url=complete_url,
        )
    # This is how Amazon computes the ETag for multipart uploads.
    md5part = hashlib.md5(bytearray(1024**2)*10).digest()
    etag_exp = hashlib.md5(md5part+md5part).hexdigest() + "-2"
    assert etag == etag_exp

    hash_exp = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_act = s3.compute_checksum(bucket_name=bucket_name,
                                   object_name=object_name)
    assert hash_exp == hash_act


def test_presigned_upload_private_by_default():
    """The presigned upload should be private by default"""
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        file_size=path.stat().st_size,
    )

    # This is what DCOR-Aid would do to upload the file
    upload_presigned_to_s3(path=path,
                           upload_urls=upload_urls,
                           complete_url=complete_url,
                           )

    s3_url = upload_urls[0].split("?")[0]

    # attempt to download the data
    response = requests.get(s3_url)
    assert not response.ok

    # make the resource public
    s3.make_object_public(object_name=object_name,
                          bucket_name=bucket_name)

    # now it should work
    response = requests.get(s3_url)
    assert response.ok


def test_presigned_upload_wrong_access():
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        file_size=path.stat().st_size,
    )

    assert len(upload_urls) == 1, "no multipart upload"
    assert complete_url is None, "no multipart upload"

    # Try to change the signature
    parts = upload_urls[0].split("&")
    for ii, part in enumerate(parts):
        if part.startswith("Signature="):
            new_sig = part[:-10] + part[-10:][::-1]
            parts[ii] = new_sig
            break
    else:
        assert False
    upload_urls[0] = "&".join(parts)

    with pytest.raises(ValueError, match="Upload failed with 403: Forbidden"):
        # This is what DCOR-Aid would do to upload the file
        upload_presigned_to_s3(path=path,
                               upload_urls=upload_urls,
                               complete_url=complete_url,
                               )


def test_presigned_upload_wrong_key():
    """Same as `test_presigned_upload_wrong_access` but no policy change"""
    path = data_path / "calibration_beads_47.rtdc"

    # This is what would happen on the server when DCOR-Aid requests an
    # upload URL
    bucket_name = f"test-circle-{uuid.uuid4()}"
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        file_size=path.stat().st_size,
    )

    assert len(upload_urls) == 1, "no multipart upload"
    assert complete_url is None, "no multipart upload"

    # Try to upload the file under a different object name
    # (this tests the S3 access restrictions)
    rid2 = str(uuid.uuid4())
    object_name_bad = f"resource/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    # replace the old with the bad object name
    upload_urls[0] = upload_urls[0].replace(object_name, object_name_bad)

    with pytest.raises(ValueError, match="Upload failed with 403: Forbidden"):
        # This is what DCOR-Aid would do to upload the file
        upload_presigned_to_s3(path=path,
                               upload_urls=upload_urls,
                               complete_url=complete_url,
                               )

    with pytest.raises(botocore.exceptions.ClientError, match="Not Found"):
        # Make sure the file does not exist
        s3.compute_checksum(bucket_name=bucket_name,
                            object_name=object_name_bad)


def test_prune_multipart_uploads():
    # Proceed as in the other tests
    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=str(uuid.uuid4()))
    rid = str(uuid.uuid4())
    object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"

    upload_urls, complete_url = s3.create_presigned_upload_urls(
        bucket_name=bucket_name,
        object_name=object_name,
        # We want two URLs
        file_size=int(1024*1024*1024 * 1.5),
        expiration=400,
    )

    # Upload 50MB of data. This is the data we want to prune.
    # Do *not* finish the multipart upload.
    requests.put(upload_urls[0],
                 data=b"0"*1024*1024*50,
                 timeout=3,
                 )

    time.sleep(1)

    # See whether the multipart upload shows up.
    prune_info = s3.prune_multipart_uploads(
        initiated_before_days=-1,
        dry_run=True,
        print_progress=True,
    )
    assert prune_info[bucket_name]["ignored"] == 0
    assert prune_info[bucket_name]["found"] == 1

    print("A")

    # Do the same thing with time>5days ago
    prune_info = s3.prune_multipart_uploads(
        initiated_before_days=5,
        dry_run=True,
        print_progress=True,
    )
    assert prune_info[bucket_name]["ignored"] == 1
    assert prune_info[bucket_name]["found"] == 0

    print("B")

    # Actually prune
    prune_info = s3.prune_multipart_uploads(
        initiated_before_days=-1,
        print_progress=True,
    )
    assert prune_info[bucket_name]["ignored"] == 0
    assert prune_info[bucket_name]["found"] == 1

    print("C")

    # And test whether that worked:
    prune_info = s3.prune_multipart_uploads(
        initiated_before_days=-1,
        print_progress=True,
    )
    assert prune_info[bucket_name]["ignored"] == 0
    assert prune_info[bucket_name]["found"] == 0


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
