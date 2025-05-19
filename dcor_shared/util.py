import hashlib


def sha256sum(path):
    """Compute the SHA256 hash of a file in 1MB chunks"""
    file_hash = hashlib.sha256()
    with open(path, "rb") as fd:
        while data := fd.read(2 ** 20):
            file_hash.update(data)
    return file_hash.hexdigest()
