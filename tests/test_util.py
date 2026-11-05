import pathlib

from dcor_shared import ckan, DC_MIME_TYPES, paths
from dcor_shared.dcinst import get_dc_instance

import pytest


def test_dc_mime_types():
    assert DC_MIME_TYPES["RT-DC"] == ".rtdc"


def test_get_ckan_config_option_from_ini(monkeypatch, tmp_path):
    ini = tmp_path / "ckan.ini"
    ini.write_text("[app:main]\nckan.storage_path = /data/ckan\n"
                   "ckan.webassets.path = /data/webassets\n")
    monkeypatch.setenv("CKAN_INI", str(ini))
    # simulate a CKAN configuration that has not been loaded
    monkeypatch.setattr("ckan.common.config", {})
    assert paths.get_ckan_config_path() == ini
    assert ckan.get_ckan_config_option("ckan.storage_path") == "/data/ckan"
    assert paths.get_ckan_storage_path() == pathlib.Path("/data/ckan")
    assert paths.get_ckan_webassets_path() == pathlib.Path("/data/webassets")


def test_get_ckan_config_path_default(monkeypatch):
    monkeypatch.delenv("CKAN_INI", raising=False)
    assert ckan.get_ckan_config_path() == pathlib.Path(
        "/etc/ckan/default/ckan.ini")


def test_get_dc_instance_missing(monkeypatch):
    monkeypatch.setattr("dcor_shared.s3cc.artifact_exists",
                        lambda rid: False)
    with pytest.raises(ValueError, match="Could not find resource"):
        get_dc_instance("6d2e6b14-6bf0-4c8b-8d2d-2e6f8f1b8f3a")
