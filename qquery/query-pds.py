#!/usr/bin/env python
from __future__ import print_function

import qquery
import json
import argparse
import datetime
import sys
import pkgutil
import importlib
import inspect
import hashlib
import os
import traceback
import re
import requests
import backoff

from redis import ConnectionPool, StrictRedis

from utilities import config, get_aois, get_redis_endpoint
from hysds_commons.job_utils import submit_mozart_job

from hysds.celery import app

REDIS_URL = get_redis_endpoint()
POOL = None


class QueryPDS(qquery.query.AbstractQuery):
    def deduplicate(self,title):
        '''
        Prevents the re-adding of sling downloads
        @params title - name of granule to check if downloading
        '''
        key = config()['dedup_redis_key_pds']
        global POOL
        if POOL is None:
            POOL = ConnectionPool.from_url(REDIS_URL)
        r = StrictRedis(connection_pool=POOL)
        return r.sadd(key,title) == 0

    def submit_sling_job(self, aoi, query_params, qtype, queue_grp, title, link, rtag=None):
        # Query for all products, and return a list of (Title,URL)
        cfg = config()  # load settings.json
        priority = query_params["priority"]
        products = query_params["products"]
        tags = query_params["tag"]

        # build payload items for job submission
        yr, mo, dy = self.getDataDateFromTitle(title)  # date
        md5 = hashlib.md5("{0}.{1}\n".format(title, self.getFileType())).hexdigest()
        repo_url = "%s/%s/%s/%s/%s/%s.%s" % (
        cfg["repository-base"], md5[0:8], md5[8:16], md5[16:24], md5[24:32], title, self.getFileType())
        location = {}
        location['type'] = 'polygon'
        location['aoi'] = aoi['id']
        location['coordinates'] = aoi['location']['coordinates']
        prod_met = {}
        prod_met['source'] = qtype
        prod_met['dataset_type'] = title[0:3]
        prod_met['spatial_extent'] = location
        prod_met['tag'] = tags

        # required params for job submission
        # if hasattr(self, 'getOauthUrl'):
        #     # sling via oauth
        #     oauth_url = self.getOauthUrl()
        #     job_type = "job:spyddder-sling-oauth_%s" % qtype
        #     job_name = "spyddder-sling-oauth_%s-%s-%s.%s" % (qtype, aoi['id'], title, self.getFileType())
        # else:
        #     # normal sling
        #     job_type = "job:spyddder-sling_%s" % qtype
        #     job_name = "spyddder-sling_%s-%s-%s.%s" % (qtype, aoi['id'], title, self.getFileType())
        #     oauth_url = None
        #TODO:rename queue
        queue = "factotum-job_worker-%s_throttled" % (qtype + str(queue_grp))  # job submission queue

        # set sling job spec release/branch
        if rtag is None:
            try:
                with open('_context.json') as json_data:
                    context = json.load(json_data)
                #TODO: rename back to new name without spyddder!
                job_spec = 'job-spyddder-sling-extract-opds:' + context['job_specification']['job-version']
            except:
                print('Failed on loading context.json')
        else:
            job_spec = 'job-spyddder-sling-extract-opds:' + rtag

        rtime = datetime.datetime.utcnow()
        job_name = "%s-%s-%s-%s-%s" % (job_spec, queue, title, rtime.strftime("%d_%b_%Y_%H:%M:%S"), aoi['id'])
        job_name = job_name.lstrip('job-')
        filename = title + "." + self.getFileType()

        # Setup input arguments here
        rule = {
            "rule_name": job_spec,
            "queue": queue,
            "priority": priority,
            "kwargs": '{}'
        }
        params = [
            {"name": "download_url",
             "from": "value",
             "value": link,
             },
            {"name": "prod_name",
             "from": "value",
             "value": "%s-pds" % title,
             },
            {"name": "file",
             "from": "value",
             "value": filename,
             },
            {"name": "prod_date",
             "from": "value",
             "value": "{}".format("%s-%s-%s" % (yr, mo, dy)),
             }
        ]
        # check for dedup, if clear, submit job
        if not self.deduplicate(filename):
            submit_mozart_job({}, rule,
                              hysdsio={"id": "internal-temporary-wiring",
                                       "params": params,
                                       "job-specification": job_spec},
                              job_name=job_name)
        else:
            print("Will not submit sling job for {0} to OpenDataset, already processed".format(title))


def parser():
    '''
    Construct a parser to parse arguments
    @return argparse parser
    '''
    parse = argparse.ArgumentParser(description="Downloads products from https://scihub.esa.int/dhus")
    parse.add_argument("-r", "--region", required=True, help="Region to submit the query for", dest="region")
    parse.add_argument("-t", "--query-type", required=True, help="Query type to find correct query handler",
                       dest="qtype")
    parse.add_argument("--tag", help="PGE docker image tag (release, version, or branch) to propagate", required=False)
    parse.add_argument("--dns_list", help="List of DNS to use as endpoint for this query, comma separated")
    # parse.add_argument("-pds", help="Sling to OpenDataset Bucket", action='store_true')

    return parse


if __name__ == "__main__":
    ''' Main program for downloading  '''
    args = parser().parse_args()
    cfg = config()
    # Detect region
    region = None

    # skip to the aoi we want
    for aoi in get_aois(cfg):
        if aoi["id"] == args.region:
            region = aoi
            break
    if region is None:
        print("Error: Failed to find appropriate aoi.", file=sys.stderr)
        exit(-1)

    try:
        print("Finding handler: {0}".format(args.qtype))
        handler = QueryPDS.getQueryHandler(args.qtype)
        handler.run(aoi, args.qtype, args.dns_list, args.tag)
        # a = AbstractQuery()
        # a.run(aoi)
    except Exception as e:
        with open('_alt_error.txt', 'a') as f:
            f.write("%s\n" % str(e))
        with open('_alt_traceback.txt', 'a') as f:
            f.write("%s\n" % traceback.format_exc())
        raise
