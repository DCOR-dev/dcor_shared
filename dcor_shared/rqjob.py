import collections
from typing import Callable, Dict, List


class RQJob:
    """Helper class for managing CKAN background jobs on DCOR

    Instead of manually enqueueing jobs in plugin.py, you can use
    this class in combination with the decorator `rqjob_register`
    below to run all jobs of your extension.

    1. Decorate each job function in your jobs.py with `@rqjob_register`,
       optionally setting keyword arguments for `RQJob`. Make sure to
       import `RQJob` in your jobs.py as well.
    2. In your plugin.py, import your `jobs.py` (to make sure that
       all methods are registered) and then in `after_resource_create`
       run `jobs.RQJob.enqueue_all_jobs(resource, ckanext="extension_name")`
    """
    _instances = []

    def __init__(self,
                 method: Callable,
                 ckanext: str,
                 queue: str = "default",
                 timeout: int = 60,
                 depends_on: List[str] = None,
                 at_front: bool = False,
                 ):
        self.method = method
        self.name = method.__name__
        self.title = method.__doc__.split("\n")[0].strip()
        self.ckanext = ckanext
        self.depends_on = depends_on or []
        self.timeout = timeout
        self.at_front = at_front
        self.queue = queue
        self._instances.append(self)

    def enqueue_job(self, resource: Dict, redis_connect=None):
        # Import here so module can be loaded without ckan available
        import ckan.plugins.toolkit as toolkit
        from ckan.lib.jobs import _connect as ckan_redis_connect
        from rq.job import Job

        if redis_connect is None:
            redis_connect = ckan_redis_connect()

        jid = f"{resource['package_id']}_{resource['position']}_"
        jid_cur = jid + self.name
        rq_args = {
            "timeout": self.timeout,
            "at_front": self.at_front,
            "job_id": jid_cur,
        }
        if self.depends_on:
            rq_args["depends_on"] = [f"{jid}_{dep}" for dep in self.depends_on]

        if not Job.exists(jid_cur, connection=redis_connect):
            toolkit.enqueue_job(self.method,
                                [resource],
                                title=self.title,
                                queue=self.queue,
                                rq_kwargs=rq_args)

    @classmethod
    def enqueue_all_jobs(cls,
                         resource: Dict,
                         ckanext: str):
        from ckan.lib.jobs import _connect as ckan_redis_connect
        redis_connect = ckan_redis_connect()

        for inst in cls._instances:
            if inst.ckanext == ckanext:
                inst.enqueue_job(resource, redis_connect=redis_connect)

    @classmethod
    def get_all_job_methods_in_order(cls, ckanext: str):
        job_dict = {}
        for job in cls._instances:
            if job.ckanext == ckanext:
                job_dict[job.name] = job

        # Order the jobs according to depends_on
        job_dict_ordered = collections.OrderedDict()
        for ii in range(len(job_dict)):
            for key in list(job_dict.keys()):
                job = job_dict[key]
                if set(job.depends_on) <= set(job_dict_ordered.keys()):
                    # All jobs this job depends on are in the ordered list
                    job_dict_ordered[key] = job
                    job_dict.pop(key)

        if job_dict:
            raise NotImplementedError(
                f"The following jobs have unmet dependencies and will not "
                f"be returned: {list(job_dict.keys())}")

        return list(job_dict_ordered.values())


class rqjob_register:
    """A decorator for background jobs to register them with RQJob"""
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __call__(self, func):
        RQJob(method=func, **self.kwargs)
        return func
