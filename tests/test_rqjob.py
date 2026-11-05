from unittest import mock
import uuid

from ckan.lib.redis import connect_to_redis

import pytest
from rq.job import Job

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
    with mock.patch("ckan.lib.redis.connect_to_redis"), \
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


def job_first(resource):
    """First job"""


def job_second(resource):
    """Second job"""


def job_third(resource):
    """Third job"""


@pytest.mark.usefixtures("clean_rqjob_instances")
def test_rqjob_enqueue_all_jobs_depends_on():
    # register in reverse order of dependencies
    RQJob(job_third, ckanext="test_ext",
          depends_on=["job_first", "job_second"])
    RQJob(job_second, ckanext="test_ext", depends_on=["job_first"])
    RQJob(job_first, ckanext="test_ext")

    pkg_id = str(uuid.uuid4())
    RQJob.enqueue_all_jobs({"package_id": pkg_id, "position": 0},
                           ckanext="test_ext")
    redis_connect = connect_to_redis()
    jobs = [Job.fetch(f"{pkg_id}_0_{name}", connection=redis_connect)
            for name in ["job_first", "job_second", "job_third"]]
    try:
        def dependencies(job):
            return sorted(dep.id for dep in job.fetch_dependencies())

        assert dependencies(jobs[0]) == []
        assert dependencies(jobs[1]) == [jobs[0].id]
        assert dependencies(jobs[2]) == sorted([jobs[0].id, jobs[1].id])
        # no worker is running, so the dependent jobs must wait
        assert jobs[0].get_status() == "queued"
        assert jobs[1].get_status() == "deferred"
        assert jobs[2].get_status() == "deferred"
    finally:
        for job in jobs:
            job.delete()
