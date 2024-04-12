"""Basic S3 utility functions"""
from __future__ import annotations

import functools
import hashlib
import json
import pathlib
import time
import traceback
from typing import List, Tuple
import warnings

import boto3
import botocore.exceptions

from .ckan import get_ckan_config_option
from .data import sha256sum


def compute_checksum(bucket_name, object_name, max_size=None):
    """Compute the SHA256 checksum of an S3 object

    The hash is computed in memory as the file is downloaded in chunks.
    """
    s3_client, _, s3_resource = get_s3()
    if max_size is None:
        obj = s3_resource.Object(bucket_name=bucket_name, key=object_name)
        max_size = obj.content_length
    hasher = hashlib.sha256()
    # This is an increment of 1MB. If you change this, please also update
    # the tests for large uploads.
    increment = 2 ** 20
    start_byte = 0
    stop_byte = min(increment, max_size)
    while start_byte < max_size:
        resp = s3_client.get_object(
            Bucket=bucket_name,
            Key=object_name,
            Range=f"bytes={start_byte}-{stop_byte}")
        content = resp['Body'].read()
        if not content:
            break
        hasher.update(content)
        start_byte = stop_byte + 1  # range is inclusive
        stop_byte = min(max_size, stop_byte + increment)
    s3_sha256 = hasher.hexdigest()
    return s3_sha256


def create_presigned_upload_urls(
        bucket_name: str,
        object_name: str,
        file_size: int,
        expiration: int = 86400) -> Tuple[List, str]:
    """Create presigned URLs for uploading an object to S3

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Name of the object
    file_size: int
        Size of the file in bytes; used to determine the number of
        multipart upload parts with a hard-coded part size of
        maximum 1 GiB. Reasons for choosing 1 GiB:
        - Using the default value of 8 or 16 MiB leads to a lot parts
          for a 20 GiB file
        - The maximum allowed part size in S3 is 5 GiB
        - Somebody on the internet said that Amazon is actually not
          concatenating the parts into a new, larger file, but it keeps
          the parts stored and just adds a layer in-between. This has
          performance implications if you are using GET with ranges
          to access partial data.
        - I was originally thinking about 100 MiB, but having the number
          of parts in the ETag as an estimate of the file size in GiB
          seemed like a good idea.
    expiration: int
        Time in seconds for the presigned URL to remain valid

    Returns
    -------
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

    Notes
    -----
    By default, due to the access design in DCOR, the S3 URLs of the
    uploaded resource is private. If you would like to make the resource
    publicly accessible, you can call the method :func:`make_object_public`,
    which will add the `public=true` tag to the object.

    Example
    -------
    To upload a file with :mod:`requests`::

        import requests

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
                    etag_part = respi.headers.get("ETag").strip("'").strip('"')
                    etags.append(etag_part)
                # Finish the multipart upload
                c_xml = "<CompleteMultipartUpload>\n"
                for ii, etag in enumerate(etags):
                    c_xml += (f"  <Part>\n"
                              + f"    <PartNumber>{ii + 1}</PartNumber>\n"
                              + f"    <ETag>{etag}</ETag>\n"
                              + f"  </Part>\n"
                              )
                c_xml += "</CompleteMultipartUpload>"
                resp = requests.post(
                    complete_url,
                    data=c_xml,
                    timeout=3,
                )
                etag_full = resp.headers.get("ETag").strip("'").strip('"')
            else:
                # Single file upload
                resp = requests.put(upload_urls[0],
                                    data=fd,
                                    timeout=3)
                etag_full = resp.headers.get("ETag").strip("'").strip('"')
    """
    require_bucket(bucket_name)
    s3_client, _, _ = get_s3()
    fields = s3_client.create_multipart_upload(Bucket=bucket_name,
                                               Key=object_name)
    upload_id = fields["UploadId"]

    gb = 1024**3

    if file_size % gb == 0:
        num_parts = file_size // gb
    else:
        num_parts = file_size // gb + 1

    upload_urls = []
    if num_parts == 1:
        # The file is uploaded with one PUT request. We don't need
        # multipart upload.
        psurl = s3_client.generate_presigned_url(
             "put_object",
             Params={'Bucket': bucket_name,
                     'Key': object_name,
                     },
             ExpiresIn=expiration,
             HttpMethod='PUT',
         )
        upload_urls.append(psurl)
        complete_url = None
    else:
        # Set up multipart upload URLs
        for ii in range(num_parts):
            psurl = s3_client.generate_presigned_url(
                     "upload_part",
                     Params={'Bucket': bucket_name,
                             'Key': object_name,
                             'UploadId': upload_id,
                             'PartNumber': ii+1
                             },
                     ExpiresIn=expiration,
                     HttpMethod='PUT',
                 )
            upload_urls.append(psurl)
        # Set up the complete upload URL
        complete_url = s3_client.generate_presigned_url(
                 "complete_multipart_upload",
                 Params={'Bucket': bucket_name,
                         'Key': object_name,
                         'UploadId': upload_id,
                         },
                 ExpiresIn=expiration,
                 HttpMethod='POST',
             )

    return upload_urls, complete_url


def create_presigned_url(
        bucket_name: str,
        object_name: str,
        expiration: int = 3600,
        filename: str | None = None):
    """Generate a presigned URL to share an S3 object

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Name of the object
    expiration: int
        Time in seconds for the presigned URL to remain valid
    filename: str
        Name of the file as it would appear in the response content
        disposition header sent by the server

    Returns
    -------
    psurl: str
        Presigned URL as string.

    Notes
    -----
    This method results in times that vary up to 10% from the `expiration`
    time in order to be able to cache the resulting URL.
    """
    now = int(create_time())
    wrap = int(expiration*.2)
    rest = now % wrap
    if rest < wrap / 2:
        t0 = now - rest
    else:
        t0 = now - rest + wrap
    return create_presigned_url_until(bucket_name=bucket_name,
                                      object_name=object_name,
                                      expires_at=t0 + expiration,
                                      filename=filename)


@functools.lru_cache()
def create_presigned_url_until(
        bucket_name: str,
        object_name: str,
        expires_at: int,
        filename: str | None = None) -> str:
    """Cached `create_presigned_url` with expiry time point

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Name of the object
    expires_at: int
        Absolute time in seconds (`time.time()`) at which the URL expires
    filename: str
        Name of the file as it would appear in the response content
        disposition header sent by the server

    Returns
    -------
    ps_url: str
        Presigned URL as string.
    """
    # Generate a presigned URL for the S3 object
    s3_client, _, _ = get_s3()
    params = {"Bucket": bucket_name,
              "Key": object_name}
    if filename is not None:
        params["ResponseContentDisposition"] = \
            f"attachment; filename = {filename}"
    ps_url = s3_client.generate_presigned_url(
        'get_object',
        Params=params,
        ExpiresIn=expires_at - create_time())
    # The response contains the presigned URL
    return ps_url


def create_time():
    return time.time()


@functools.lru_cache()
def get_s3():
    """Return the current S3 client as defined by ckan.ini"""
    # Create a new session (do not use the default session)
    s3_session = boto3.Session(
        aws_access_key_id=get_ckan_config_option(
            "dcor_object_store.access_key_id"),
        aws_secret_access_key=get_ckan_config_option(
            "dcor_object_store.secret_access_key"),
    )
    ssl_verify = get_ckan_config_option(
        "dcor_object_store.ssl_verify").lower() == "true"
    s3_client = s3_session.client(
        service_name='s3',
        use_ssl=ssl_verify,
        verify=ssl_verify,
        endpoint_url=get_ckan_config_option("dcor_object_store.endpoint_url"),
    )
    s3_resource = s3_session.resource(
        service_name="s3",
        use_ssl=ssl_verify,
        verify=ssl_verify,
        endpoint_url=get_ckan_config_option("dcor_object_store.endpoint_url"),
    )
    return s3_client, s3_session, s3_resource


def is_available():
    """Return True if S3 credentials have been specified"""
    s3_key_id = get_ckan_config_option("dcor_object_store.access_key_id")
    s3_secret = get_ckan_config_option("dcor_object_store.secret_access_key")
    return s3_key_id and s3_secret


def make_object_public(bucket_name, object_name, missing_ok=False):
    """Make an S3 object public by setting the public=true tag

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Key of the object in the bucket
    missing_ok: bool
        Whether to raise S3.Client.exceptions.NoSuchKey or ignore
        missing `object_name`
    """
    s3_client, _, _ = get_s3()
    try:
        response = s3_client.get_object_tagging(
            Bucket=bucket_name,
            Key=object_name)
    except (s3_client.exceptions.NoSuchBucket,
            s3_client.exceptions.NoSuchKey):
        if not missing_ok:
            raise
    else:
        tags = []
        for item in response["TagSet"]:
            tags.append(f"{item['Key']}={item['Value']}")
        if not tags.count("public=true"):
            for retry in range(5):
                try:
                    s3_client.put_object_tagging(
                        Bucket=bucket_name,
                        Key=object_name,
                        Tagging={
                            'TagSet': [
                                {
                                    'Key': 'public',
                                    'Value': 'true',
                                },
                            ],
                        },
                    )
                except botocore.exceptions.ClientError:
                    trcbck = traceback.format_exc()
                    continue
                else:
                    break
            else:
                raise ValueError(f"Encountered Error:\n{trcbck}")


def object_exists(bucket_name, object_name):
    """Check whether an object exists"""
    s3_client, _, _ = get_s3()
    try:
        s3_client.head_object(Bucket=bucket_name, Key=object_name)
    except (s3_client.exceptions.NoSuchKey,
            s3_client.exceptions.ClientError):
        obj_exists = False
    else:
        obj_exists = True
    return obj_exists


@functools.lru_cache()
def require_bucket(bucket_name):
    """Create an S3 bucket if it does not exist yet

    Parameters
    ----------
    bucket_name: str
        Bucket to create

    Notes
    -----
    Buckets are created with the following Access Policy (only objects
    with the tag "public" set to "true" are publicly accessible)::

        {
            "Version": "2012-10-17",
            "Statement": [
             {
              "Sid": "Allow anonymous access to objects with public:true tag",
              "Effect": "Allow",
              "Action": ["s3:GetObject"],
              "Resource": ["arn:aws:s3:::*"],
              "Principal": "*",
              "Condition": {
                "StringEquals": {
                "s3:ExistingObjectTag/public": ["true"]
                }
              }
            }
          ]
        }
    """
    # Define bucket policy
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "Allow anonymous access to objects with public:true tag",
            # allow access given the following conditions
            "Effect": "Allow",
            # affects all objects in this bucket
            "Resource": f"arn:aws:s3:::{bucket_name}/*",
            # download the object
            "Action": ["s3:GetObject"],
            # anonymous access
            "Principal": "*",
            # only for objects with the public:true tag
            "Condition": {
                "StringEquals": {"s3:ExistingObjectTag/public": ["true"]}
            }}],
    }
    # Convert the policy from dict to JSON string
    bucket_policy = json.dumps(bucket_policy)

    s3_client, _, s3_resource = get_s3()
    # Create the bucket (this will return the bucket if it already exists)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/
    # services/s3/client/create_bucket.html
    s3_bucket = s3_resource.Bucket(bucket_name)
    creation_date = None
    try:
        creation_date = s3_bucket.creation_date
    except botocore.exceptions.ClientError:
        # Happens with swift on OpenStack when the bucket does not exist.
        # Does not happen with minIO (creation_date just returns None there).
        pass
    if creation_date is None:
        try:
            s3_bucket.create()
        except s3_client.exceptions.NoSuchBucket:
            warnings.warn(f"The bucket {bucket_name} already exists. I will "
                          f"try to upload the resource anyway.")
        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=bucket_policy)
    return s3_bucket


def upload_file(bucket_name, object_name, path, sha256=None, private=True,
                override=False):
    """Upload a file to a bucket

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Path/name to the object in the bucket
    path: str or pathlib.Path
        Local path of the file to be uploaded
    sha256: str
        SHA256 checksum of the file to be uploaded, will be computed
        if not provided
    private: bool
        Whether the object should remain private. If set to False,
        a tag "public:true" is added to the object which is picket up
        by the bucket policy defined in :func:`require_bucket`.
    override: bool
        Whether to override existing objects in s3

    Returns
    -------
    s3_url: str
        URL to the S3 object
    """
    if not sha256:
        sha256 = sha256sum(path)

    path_size = pathlib.Path(path).stat().st_size
    s3_client, _, _ = get_s3()
    s3_bucket = require_bucket(bucket_name)

    perform_upload = True
    if not override:
        perform_upload = not object_exists(bucket_name=bucket_name,
                                           object_name=object_name)

    if perform_upload:
        s3_bucket.upload_file(Filename=str(path),
                              Key=object_name,
                              # ExtraArgs={
                              # # verification of the upload (breaks OpenStack)
                              # "ChecksumAlgorithm": "SHA256",
                              # # This is not supported in MinIO:
                              # "ChecksumSHA256": sha256
                              # }
                              )
        # Make sure the upload worked properly by computing the SHA256 sum.
        s3_sha256 = compute_checksum(bucket_name=bucket_name,
                                     object_name=object_name,
                                     max_size=path_size)
        if sha256 != s3_sha256:
            raise ValueError(
                f"Checksum mismatch for {bucket_name}:{object_name}!")

        if not private:
            # If the resource is not private, add a tag, so it is picked up
            # by the bucket policy for public accessibility.
            make_object_public(bucket_name=bucket_name,
                               object_name=object_name)

    endpoint_url = get_ckan_config_option("dcor_object_store.endpoint_url")
    object_loc = f"{endpoint_url}/{bucket_name}/{object_name}"
    return object_loc
