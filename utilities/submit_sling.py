#!/usr/bin/env python

'''
Submits a sling job for the input acqusition via a REST call
'''

import re
import os
import json
import glob
import argparse

mozart_url = 'https://jobs.grfn.hysds.io/mozart/api/v0.2/job/submit'

def submit_sling_job(filename=None, download_url=None, queue=None, release=None, priority=None, dedup=None, tags=None):
    # parse params from obj
    search = os.path.join(os.getcwd(), '*.dataset.json')
    ds_file = glob.glob(search)[0]
    with open(ds_file) as params_file:    
        ds = json.load(params_file)

    #add additional params
    ds['dataset_type'] =  'S1A'
    ds['source'] = 'scihub'
    job_name = 'job-sling'
    download_url = download_url
    filename = filename
    dtrslt = re.search('(20\d{2})(\d{2})(\d{2})', filename)
    date = '%s-%s-%s' % (dtrslt.group(1), dtrslt.group(2), dtrslt.group(3))
    if tags == None:
        tags_string = ""
    else:
        tags_string = ' --tags "%s"' % tags
    #params for sling 
    params = {
    "download_url": download_url,
    "repo_url": 'https://aria-alt-dav.jpl.nasa.gov/incoming/%s' % filename,
    "prod_name": filename,
    "file_type": 'zip',
    "prod_date": date,
    "prod_met": ds,
    "options": "--force_extract"
    }

    #save the params as params.json
    params_fn = 'params.json'
    with open(params_fn, 'w') as fp:
        json.dump(params, fp)
    dir_path = os.path.dirname(os.path.realpath(__file__))

    command = dir_path + '/submit_job.py --queue "%s" --mozart_url "%s" --job_name "%s" --release "%s" --priority "%s" --dedup "%s"%s --params "%s"' % (queue,mozart_url, job_name, release, priority, dedup, tags_string, params_fn)
    print(command)
    os.system(command)
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--filename', help='filename of download', dest='filename', required=True)
    parser.add_argument('-u', '--download_url', help='download url of product', dest='download_url', required=True)
    parser.add_argument('-q', '--queue', help='queue to submit the sling job to', dest='queue', required=True)
    parser.add_argument('-r', '--release', help='job release tag (aka master, release-20170901)', dest='release', required=True)
    parser.add_argument('-p', '--priority', help='priority to run the sling job', dest='priority', required=False, default='5')
    parser.add_argument('-d', '--dedup', help='whether or not to run dedup', dest='dedup', required=False, default=True)
    parser.add_argument('-t', '--tags', help='optional tags (separate by commas)', dest='tags', required=False, default=None)
    args = parser.parse_args()
    submit_sling_job(filename=args.filename, download_url=args.download_url, queue=args.queue, release=args.release, priority=args.priority, dedup=args.dedup, tags=args.tags)
