import pathlib
import uuid

from ckan import logic

import pytest

from dcor_shared import get_resource_path, sha256sum, wait_for_resource


def test_sha256sum(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("Sum this up!")
    ist = sha256sum(p)
    soll = "d00df55b97a60c78bbb137540e1b60647a5e6b216262a95ab96cafd4519bcf6a"
    assert ist == soll


def test_wait_for_resource_s3(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id,
                            "s3_available": True})
    # Should not raise an exception
    wait_for_resource(res_id)


@pytest.mark.ckan_config('ckan.plugins', '')  # disable plugins
def test_wait_for_resource_no_s3_url_no_plugins(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Create the actual path
    rp = pathlib.Path(get_resource_path(res_id))
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_bytes(b"This is not a dummy file, but a fake DC file!")
    # Should not raise an exception
    wait_for_resource(res_id)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot')
def test_wait_for_resource_no_s3_url_with_dcor_depot_plugin(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Create the actual path
    rp = pathlib.Path(get_resource_path(res_id))
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_bytes(b"This is not a dummy file, but a fake DC file!")
    rp2 = rp.with_name("test.rtdc")
    rp.rename(rp2)
    rp.symlink_to(rp2)

    # Should not raise an exception
    wait_for_resource(res_id)


def test_wait_resource_not_available(monkeypatch):
    res_id = str(uuid.uuid4())
    monkeypatch.setattr(logic, "get_action",
                        lambda x: lambda context, data_dict: {
                            "id": res_id})
    # Should raise an exception
    with pytest.raises(OSError, match="Data import seems to take too long"):
        wait_for_resource(res_id, timeout=1)
