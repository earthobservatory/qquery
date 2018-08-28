#!/usr/bin/env python

'''
Submits a job via a REST call
'''

import json
import os
import argparse
import requests

def main(queue=None, mozart_url=None, job_name=None, release=None, priority='5',
     dedup=True, tags=None, params=None):
    '''
    submits a job via requests call
    '''
    #parse params
    if queue == None:
        raise Exception('no input job queue.')
    if mozart_url == None:
        raise Exception('no mozart api job submission url given')
    if job_name == None:
        raise Exception('no job_name input')
    if release == None:
        raise Exception('no release version input')
    #parse tags
    if tags == None:
        tag_string = '[]'
    else:
        tag_string = '["%s"]' % '","'.join(tags.split(','))
    if params == None:
        output_params = '{}'
    else:
        try:
            #load and dump into string to validate
            params_payload = json.loads(params)
            output_params = json.dumps(params_payload)
        except:
            #try it as a path
            try:
                if os.path.exists(params):
                    with open(params) as params_file:    
                        params_payload = json.load(params_file)
                    output_params = json.dumps(params_payload)
                else:
                    raise Exception('params input does not exist or cannot be parsed.')
            except:
                raise Exception('input params could not be parsed.')
    # submit mozart job
    params = {
        'queue': queue,
        'priority': priority,
        'tags': tag_string,
        'type': '%s:%s' % (job_name, release),
        'params': output_params,
        'enable_dedup': dedup
    }
    print('submitting job %s:%s with params: %s' % (job_name, release, json.dumps(params)) )
    r = requests.post(mozart_url, params=params, auth=None, verify=False)
    if r.status_code != 200:
        r.raise_for_status()
    result = r.json()
    if 'result' in result.keys() and 'success' in result.keys():
        if result['success'] == True:
            job_id = result['result']
            print 'submitted %s:%s as job_id: %s' % (job_name, release, job_id)
        else:
            print 'job not submitted successfully: %s' % result
            raise Exception('job not submitted successfully: %s' % result)
    else:
        raise Exception('job not submitted successfully: %s' % result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-q', '--queue', help='queue to submit the sling job to', dest='queue', required=True)
    parser.add_argument('-m', '--mozart_url', help='full url of mozart api', dest='mozart_url', required=True)
    parser.add_argument('-n', '--job_name', help='job name', dest='job_name', required=True)
    parser.add_argument('-r', '--release', help='job release tag (aka master, release-20170901)', dest='release', required=True)
    parser.add_argument('-p', '--priority', help='priority to run the sling job', dest='priority', required=False, default='5')
    parser.add_argument('-d', '--dedup', help='whether or not to run dedup', dest='dedup', required=False, default=True)
    parser.add_argument('-t', '--tags', help='optional tags (separate by commas)', dest='tags', required=False, default=None)
    parser.add_argument('-a', '--params', help='input params (json string or path to json file)', dest='params', required=False, default=None)
    args = parser.parse_args()
    main(queue=args.queue, mozart_url=args.mozart_url, job_name=args.job_name, release=args.release, priority=args.priority,
     dedup=args.dedup, tags=args.tags, params=args.params)