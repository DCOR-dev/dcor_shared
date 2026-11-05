from unittest import mock

import pytest

from dcor_shared import RQJob, rqjob_register


@pytest.fixture
def clean_rqjob_instances(monkeypatch):
    monkeypatch.setattr(RQJob, "_instances", [])


def job_a(resource):
    """Run job A

    More details
    """


def job_b(resource):
    """Run job B"""


def job_c(resource):
    """Run job C"""


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_register():
    func = rqjob_register(ckanext="test_ext", queue="dcor-normal",
                          timeout=120)(job_a)
    assert func is job_a
    job, = RQJob._instances
    assert job.method is job_a
    assert job.name == "job_a"
    assert job.title == "Run job A"
    assert job.ckanext == "test_ext"
    assert job.queue == "dcor-normal"
    assert job.timeout == 120
    assert job.depends_on == []
    assert not job.at_front


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_get_all_job_methods_in_order():
    # register in reverse order of dependencies
    RQJob(job_c, ckanext="test_ext", depends_on=["job_b"])
    RQJob(job_b, ckanext="test_ext", depends_on=["job_a"])
    RQJob(job_a, ckanext="test_ext")
    RQJob(job_a, ckanext="other_ext")
    jobs = RQJob.get_all_job_methods_in_order(ckanext="test_ext")
    assert [j.name for j in jobs] == ["job_a", "job_b", "job_c"]


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_get_all_job_methods_in_order_unmet_dependency():
    RQJob(job_a, ckanext="test_ext")
    RQJob(job_b, ckanext="test_ext", depends_on=["job_unknown"])
    with pytest.raises(NotImplementedError, match="job_b"):
        RQJob.get_all_job_methods_in_order(ckanext="test_ext")


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_enqueue_all_jobs():
    RQJob(job_a, ckanext="test_ext", queue="dcor-short", at_front=True)
    RQJob(job_b, ckanext="test_ext", timeout=10)
    RQJob(job_c, ckanext="other_ext")
    resource = {"package_id": "pkg", "position": 0}
    with mock.patch("ckan.lib.jobs._connect"), \
            mock.patch("rq.job.Job.exists", return_value=False), \
            mock.patch("ckan.plugins.toolkit.enqueue_job") as enqueue_job:
        RQJob.enqueue_all_jobs(resource, ckanext="test_ext")
    assert enqueue_job.call_count == 2
    call_a, call_b = enqueue_job.call_args_list
    assert call_a.args == (job_a, [resource])
    assert call_a.kwargs["title"] == "Run job A"
    assert call_a.kwargs["queue"] == "dcor-short"
    assert call_a.kwargs["rq_kwargs"] == {
        "timeout": 60, "at_front": True, "job_id": "pkg_0_job_a"}
    assert call_b.kwargs["rq_kwargs"] == {
        "timeout": 10, "at_front": False, "job_id": "pkg_0_job_b"}


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_enqueue_job_exists():
    job = RQJob(job_a, ckanext="test_ext")
    with mock.patch("rq.job.Job.exists", return_value=True), \
            mock.patch("ckan.plugins.toolkit.enqueue_job") as enqueue_job:
        job.enqueue_job({"package_id": "pkg", "position": 0},
                        redis_connect=mock.MagicMock())
    enqueue_job.assert_not_called()
