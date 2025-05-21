import functools
import time

from . import s3cc
from .util import sha256sum  # noqa: F401


@functools.lru_cache(maxsize=100)
def wait_for_resource(resource_id: str,
                      timeout: float = 10):
    """Wait for resource to be available

    This function can be used by other plugins to ensure that
    a resource is available for processing.

    The only way (since 2024) of uploading data is via pre-signed URLs
    to an S3 instance. Here, we have to make sure that the
    upload is complete and the file exists. If this is the case,
    then uploads should have already completed when this function
    is called, so we only check for the existence of the resource
    in ckan and whether the `s3_available` attribute is defined.
    """
    from ckan import logic

    if len(resource_id) != 36:
        raise ValueError(f"Invalid resource id: {resource_id}")

    resource_show = logic.get_action("resource_show")

    t0 = time.time()
    while True:
        try:
            res_dict = resource_show(context={'ignore_auth': True,
                                              'user': 'default'},
                                     data_dict={"id": resource_id})
        except logic.NotFound:
            # Other processes are still working on getting the resource
            # online. We have to wait.
            time.sleep(5)
            continue

        # object exists in database?
        s3_ok = res_dict.get("s3_available", None)
        if s3_ok:
            # If the resource is on S3, it is considered to be available.
            break

        # object exists on S3?
        try:
            s3_exist = s3cc.artifact_exists(res_dict["id"])
        except BaseException:
            s3_exist = False
        if s3_exist:
            break

        if time.time() - t0 > timeout:
            raise OSError(f"Data import seems to take too long "
                          f"for '{resource_id}'!")
