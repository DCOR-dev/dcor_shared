from . import s3cc


def get_dc_instance(rid):
    """Return an instance of dclab's `RTDCBase` for a resource identifier"""
    # The resource must be on S3
    if s3cc.artifact_exists(rid):
        return s3cc.get_s3_dc_handle(rid)
    else:
        raise ValueError(f"Could not find resource {rid} anywhere")
