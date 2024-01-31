import functools
import hashlib
import pathlib
import time
import warnings

from .ckan import get_resource_path


#: Content of the dummy file created when importing data.
DUMMY_BYTES = b"[Data import pending]"


def sha256sum(path):
    """Compute the SHA256 hash of a file in 1MB chunks"""
    file_hash = hashlib.sha256()
    with open(path, "rb") as fd:
        while data := fd.read(2 ** 20):
            file_hash.update(data)
    return file_hash.hexdigest()


@functools.lru_cache(maxsize=100)
def wait_for_resource(resource_id: str,
                      timeout: float = 10):
    """Wait for resource to be available

    This function can be used by other plugins to ensure that
    a resource is available for processing.

    There multiple ways for data to become available:

    1. The ckanext-dcor_depot plugin imports data by touching
       dummy files and then sym-linking to data on disk. Here
       we just check that the file is not a dummy file anymore.
    2. Legacy uploads via nginx/uwsgi directly into CKAN and onto
       the local block storage worked the same way. We have to wait
       for the dummy file to be replaced.
    3. The new (2024) way of uploading data is via pre-signed URLs
       to an S3 instance. Here, we have to make sure that the
       upload is complete and the file exists. If this is the case,
       then uploads should have already completed when this function
       is called, so we only check for the existence of the resource
       in ckan and whether the `s3_available` attribute is defined.
    """
    from ckan.common import config
    from ckan import logic

    if len(resource_id) != 36:
        warnings.warn("Please pass the CKAN resource id as `resource_id` "
                      "instead of a string or a path. This will raise an "
                      "exception in the future.",
                      DeprecationWarning)
        # The user passed a local path on the block storage. These look like
        # this: /data/dcor-instance/resources/RE/SO/URCE-ID
        resource_id = "".join(resource_id.split("/")[-3])

    resource_show = logic.get_action("resource_show")
    path = pathlib.Path(get_resource_path(resource_id))

    dcor_depot_available = "dcor_depot" in config.get('ckan.plugins', "")
    # Initially this was set to 10s, but if `/data` is mounted on a
    # network share then this part here just takes too long.
    t0 = time.time()
    ld = len(DUMMY_BYTES)
    while True:
        res_dict = resource_show(context={'ignore_auth': True,
                                          'user': 'default'},
                                 data_dict={"id": resource_id})

        s3_ok = res_dict.get("s3_available", None)
        if time.time() - t0 > timeout:
            raise OSError("Data import seems to take too long "
                          "for '{}'!".format(path))
        elif s3_ok is not None:
            # If the dataset is on S3, it is considered to be available.
            break
        elif not path.exists():
            time.sleep(0.05)
            continue
        elif dcor_depot_available and not path.is_symlink():
            # Resource is only available when it is symlinked by
            # the ckanext.dcor_depot `symlink_user_dataset` job
            # (or by the ckanext.dcor_depot importers).
            time.sleep(0.05)
            continue
        elif path.stat().st_size == ld and path.read_bytes() == DUMMY_BYTES:
            # wait a bit
            time.sleep(0.01)
            continue
        else:
            # not a dummy file
            break
