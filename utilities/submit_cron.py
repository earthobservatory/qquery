#!/usr/bin/env python
import os, sys, re, json, requests
from hysds.orchestrator import submit_job
from hysds.log_utils import logger as logging

def main(repo_name):
    payload = {
        "job_type": "job:cron:master",
         "payload": {
             "qtype": str(repo_name)
        }
    }
    print "Submitting cron: ",repo_name,"job"
    submit_job.apply_async((payload,), queue='jobs_processed')

if __name__ == "__main__":
    main(sys.argv[1])
