import pathlib
import pytest

import ckan.tests.factories as factories
import requests

from dcor_shared.testing import make_dataset_via_s3
from dcor_shared import s3cc, sha256sum

data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_make_dataset_via_s3():
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    ds_dict = make_dataset_via_s3(create_context, owner_org, activate=False)
    assert ds_dict["state"] == "draft"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_make_dataset_with_resource_via_s3(tmp_path):
    # upload a *valid* [sic] .rtdc File (this is the control)
    ds_dict, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True,
        private=False,
    )
    assert len(ds_dict["resources"]) == 1
    assert "id" in res_dict
    assert res_dict["package_id"] == ds_dict["id"]

    # verify SHA256 sum of the resource
    ps_url = s3cc.get_s3_url_for_artifact(res_dict["id"], artifact="resource")
    response = requests.get(ps_url)
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)

    assert sha256sum(dl_path) == \
           "490efdf5d9bb4cd4b2a6bcf2fe54d4dc201c38530140bcb168980bf8bf846c73"
