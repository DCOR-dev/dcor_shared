import functools
import hashlib
import json
import pathlib
import warnings

import boto3
import botocore.exceptions

from .ckan import get_ckan_config_option


def create_presigned_url(bucket_name, object_name, expiration=3600):
    """Generate a presigned URL to share an S3 object

    Parameters
    ----------
    bucket_name: str
        Name of the bucket
    object_name: str
        Name of the object
    expiration: int
        Time in seconds for the presigned URL to remain valid

    Returns
    -------
    psurl: str
        Presigned URL as string.
    """
    # Generate a presigned URL for the S3 object
    s3_client, _, _ = get_s3()
    psurl = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': object_name},
        ExpiresIn=expiration)
    # The response contains the presigned URL
    return psurl


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


def make_object_public(bucket_name, object_name):
    s3_client, _, _ = get_s3()
    response = s3_client.get_object_tagging(
        Bucket=bucket_name,
        Key=object_name)
    tags = []
    for item in response["TagSet"]:
        tags.append(f"{item['Key']}={item['Value']}")
    if not tags.count("public=true"):
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


def upload_file(bucket_name, object_name, path, sha256, private=True):
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
        SHA256 checksum of the file to be uploaded
    private: bool
        Whether the object should remain private. If set to False,
        a tag "public:true" is added to the object which is picket up
        by the bucket policy defined in :func:`require_bucket`.

    Returns
    -------
    s3_url: str
        URL to the S3 object
    """
    path_size = pathlib.Path(path).stat().st_size
    s3_client, _, _ = get_s3()
    s3_bucket = require_bucket(bucket_name)
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
    # Download the file directly into the hasher.
    hasher = hashlib.sha256()
    # This is an increment of 1MB. If you change this, please also update
    # the tests for large uploads.
    increment = 2**20
    start_byte = 0
    max_size = path_size
    stop_byte = min(increment, max_size)
    while start_byte < max_size:
        resp = s3_client.get_object(Bucket=bucket_name,
                                    Key=object_name,
                                    Range=f"bytes={start_byte}-{stop_byte}")
        content = resp['Body'].read()
        if not content:
            break
        hasher.update(content)
        start_byte = stop_byte + 1  # range is inclusive
        stop_byte = min(max_size, stop_byte + increment)
    s3_sha256 = hasher.hexdigest()
    if sha256 != s3_sha256:
        raise ValueError(f"Checksum mismatch for {bucket_name}:{object_name}!")

    if not private:
        # If the resource is not private, add a tag, so it is picked up
        # by the bucket policy for public accessibility.
        make_object_public(bucket_name=bucket_name,
                           object_name=object_name)

    endpoint_url = get_ckan_config_option("dcor_object_store.endpoint_url")
    return f"{endpoint_url}/{bucket_name}/{object_name}"