from dclab.rtdc_dataset import RTDC_HDF5

from .ckan import get_resource_path
from . import s3cc


def get_dc_instance(rid):
    """Return an instance of dclab's `RTDCBase` for a resource identifier"""
    # Try local file first
    path = get_resource_path(rid)
    if path.is_file():
        # Disable basins, because they could point to files on the local
        # file system (security).
        return RTDC_HDF5(path, enable_basins=False)
    else:
        # The resource must be on S3
        if s3cc.artifact_exists(rid):
            return s3cc.get_s3_dc_handle(rid)
        else:
            raise ValueError(f"Could not find resource {rid} anywhere")
