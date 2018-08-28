from __future__ import print_function

import os
import sys
import json

import requests
from requests.auth import HTTPBasicAuth
from hysds.celery import app
from hysds_commons.net_utils import get_container_host_ip

def config():
    '''
    Reads the settings JSON file out of the config directory
    @returns: parsed JSON object
    '''
    try:
        path=os.path.join(os.path.dirname(os.path.realpath(__file__)),"config/settings.json")
        with open(path,"r") as handel:
            return json.load(handel)
    except:
        print("Failed to load JSON file:",path,file=sys.stderr)

def get_aois(cfg):
    '''
    Gets the AoIs from the elasi-search backend
    @param: cfg - configuration
    @returns: list of AoI objects
    '''
    es_url = app.conf.GRQ_ES_URL
    index = cfg['aoi_index']
    search_url = "%s/%s/_search?search_type=scan&scroll=10m&size=100" % (es_url, index)
    r = requests.post(search_url, data=json.dumps({"query":{"match_all":{}}}))
    r.raise_for_status()
    scan_result = r.json()
    count = scan_result['hits']['total']
    scroll_id = scan_result['_scroll_id']
    results = []
    while True:
        r = requests.post("%s/_search/scroll?scroll=10m" % es_url, data=scroll_id)
        r.raise_for_status()
        res = r.json()
        scroll_id = res['_scroll_id']
        if len(res['hits']['hits']) == 0: break
        for hit in res['hits']['hits']:
            results.append(hit['_source'])
    return results

def get_redis_endpoint():
    """Return redis endpoint running on container host if running within a container
       or localhost if otherwise."""

    return "redis://%s" % get_container_host_ip()
