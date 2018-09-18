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

class AbstractQuery(object):
    '''
    A class holding all generic query functions
    '''

    @classmethod
    def getQueryHandler(clazz,qtype):
        '''
        Get a handler for this particular query type by searching registered subclasses
        @param qtype - type of query
        '''
        try:
            mod = importlib.import_module(qtype)
            return mod.getHandler()
        except Exception as e:
            raise UnsupportedQueryTypeException("Cannot find handler for: "+qtype+" due to exception: "+str(e))

    @classmethod
    def search(clazz,path):
        '''
        Recurse and load modules
        @param mod - mod to import
        '''
        for importer, name, ispkg in pkgutil.walk_packages(path):
            if ispkg:
                continue
            module = importer.find_module(name).load_module(name)
            for name, claz in inspect.getmembers(module):
                if not inspect.isclass(claz) or not issubclass(claz, qquery.query.AbstractQuery):
                    continue
                return clazz
                
    def deduplicate(self,title):
        '''
        Prevents the re-adding of sling downloads
        @params title - name of granule to check if downloading
        '''
        key = config()['dedup_redis_key']
        global POOL
        if POOL is None:
            POOL = ConnectionPool.from_url(REDIS_URL)
        r = StrictRedis(connection_pool=POOL)
        return r.sadd(key,title) == 0
        
    @backoff.on_exception(backoff.expo, requests.exceptions.RequestException,
                          max_tries=8, max_value=32)
    def query_results(self, start_time, end_time, aoi, mapping=None):
        '''
        Query results from endpoint with jittering.
        '''
        return self.query(start_time, end_time, aoi, mapping=mapping)

    def run(self, aoi, input_qtype, dns_list_str, rtag=None):
        '''
        Run the overall query. Should not be overridden.
        '''
        #determine config parameters
        query_params = self.parse_params(aoi, input_qtype, dns_list_str)
        if query_params == None:
            print("Failed to parse params properly")
            print("aoi:",aoi)
            print("params:",query_params)
            return
        start_time = query_params["starttime"]
        end_time = query_params["endtime"]
        products = query_params["products"]
        dns_list = query_params["dns_list"]

        #counter for rotating between DNS and queues for sling downloads, so as to overcome per account download limits
        num_queue = 0
        num_dns = len(dns_list)

        #each products contains a specific mapping for the query
        for product in products:
            print("querying %s for %s products from %s to %s" % (input_qtype, product, start_time, end_time))
            try:
            	results = self.query_results(start_time,end_time,aoi,mapping=product)
            	print("returned %s results" % str(len(results)))
                for title,link in results:
                    # rotate dns in dns_list by replacing dns in link
                    num_queue += 1
                    queue_grp = (num_queue % num_dns) + 1
                    new_dns_link = re.sub('(?<=https:\/\/).*?(?=\/)', dns_list[queue_grp-1], link)

                    print("submitting sling for endpoint: %s, queuegrp:%s, url: %s aliased to %s"
                          % (input_qtype, queue_grp, link, new_dns_link))
                    self.submit_sling_job(aoi, query_params, input_qtype, queue_grp, title, new_dns_link, rtag)

            except QueryBadResponseException as qe:
                print("Error: Failed to query properly. {0}".format(str(qe)),file=sys.stderr)
                raise qe
            #save time of query
            stamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            self.saveStamp(stamp,self.stampKeyname(aoi,input_qtype))


    def submit_sling_job(self, aoi, query_params, qtype, queue_grp, title, link, rtag=None):
        #Query for all products, and return a list of (Title,URL)
        cfg = config() #load settings.json
        priority = query_params["priority"]
        products = query_params["products"]
        tags = query_params["tag"]

        #build payload items for job submission
        yr, mo, dy = self.getDataDateFromTitle(title) #date
        md5 = hashlib.md5("{0}.{1}\n".format(title,self.getFileType())).hexdigest()
        repo_url = "%s/%s/%s/%s/%s/%s.%s" % (cfg["repository-base"],md5[0:8],md5[8:16],md5[16:24],md5[24:32],title,self.getFileType())
        location = {}
        location['type'] = 'polygon'
        location['aoi'] = aoi['id']
        location['coordinates'] = aoi['location']['coordinates']
        prod_met = {}
        prod_met['source'] = qtype
        prod_met['dataset_type'] = title[0:3]
        prod_met['spatial_extent'] = location
        prod_met['tag'] = tags
        
        #required params for job submission
        if hasattr(self, 'getOauthUrl'):
            #sling via oauth
            oauth_url = self.getOauthUrl()
            job_type = "job:spyddder-sling-oauth_%s" % qtype
            job_name = "spyddder-sling-oauth_%s-%s-%s.%s" % (qtype,aoi['id'],title,self.getFileType())
        else:
            #normal sling
            job_type = "job:spyddder-sling_%s" % qtype
            job_name = "spyddder-sling_%s-%s-%s.%s" % (qtype,aoi['id'],title,self.getFileType())
            oauth_url = None
        queue = "factotum-job_worker-%s_throttled" % (qtype+str(queue_grp)) # job submission queue
        
        #set sling job spec release/branch
        if rtag is None:
            try:
                with open('_context.json') as json_data:
                    context = json.load(json_data)
                job_spec = 'job-sling:'+context['job_specification']['job-version']
            except:
                print('Failed on loading context.json')
        else: job_spec = 'job-sling:'+rtag
        
        rtime = datetime.datetime.utcnow()
        job_name = "%s-%s-%s-%s-%s" % (job_spec,queue,title,rtime.strftime("%d_%b_%Y_%H:%M:%S"),aoi['id'])
        job_name = job_name.lstrip('job-')

        #Setup input arguments here
        rule = {
            "rule_name": job_spec,
            "queue": queue,
            "priority": priority,
            "kwargs":'{}'
        }
        params = [
            { "name": "download_url",
              "from": "value",
              "value": link,
            },
            { "name": "repo_url",
              "from": "value",
              "value": repo_url,
            },
            { "name": "prod_name",
              "from": "value",
              "value": title,
            },
            { "name": "file_type",
              "from": "value",
              "value": self.getFileType(),
            },
            { "name": "prod_date",
              "from": "value",
              "value": "{}".format("%s-%s-%s" % (yr, mo, dy)),
            },
            { "name": "prod_met",
              "from": "value",
              "value": prod_met,
            },
            { "name": "options",
              "from": "value",
              "value": "--force_extract"
            }
        ]
        #check for dedup, if clear, submit job
        if not self.deduplicate(title+"."+self.getFileType()):
            submit_mozart_job({}, rule,
                hysdsio={"id": "internal-temporary-wiring",
                        "params": params,
                        "job-specification": job_spec},
                job_name=job_name)
        else:
            print("Will not submit sling job for {0}, already processed".format(title))
        



    def parse_params(self, aoi, input_qtype, dns_list_str):
        '''
        parses the parameters from the aoi, determines proper start/end times and returns a dict object containing params
        '''
        params = {} #dict to be returned holding parsed query parameters
        cfg = config() #load settings.json
        #determine if end_time has passed, therefore query is expired
        if "temporal" in aoi.keys() and "endquery" in aoi["temporal"].keys():
            if determine_if_expired_query(aoi["temporal"]["endquery"]):
                return None
        if "endquery" in aoi.keys() and determine_if_expired_query(aoi["endquery"]):
            return None
        #map the values outside the endpoint specific settings
        #default to looking back window_size days from settings config file, unless window_size is in the aoi
        if "window_size" in aoi.keys():
            window = aoi["window_size"]
        else:
            window = cfg["window-size-days"]
        end_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") #default end time is now
        #default start time is now - window size
        start_time = (datetime.datetime.utcnow() - datetime.timedelta(days=float(window))).strftime("%Y-%m-%dT%H:%M:%S")
        #but if the endpoint aoi is not in redis, default to retrieving everything
        last_query_time = self.loadStamp(self.stampKeyname(aoi,input_qtype))
        if last_query_time is None:
            start_time = "1970-01-01T00:00:00"
        else:
            start_time = last_query_time
        #determine if there is an event time
        event_time = None
        #check aoi
        if "event" in aoi.keys() and "time" in aoi["event"].keys():
            event_time = parse_datetime(aoi["event"]["time"])
        #check aoi["metadata"]
        if "metadata" in aoi.keys() and "event" in aoi["metadata"] and "time" in aoi["metadata"]["event"].keys():
            event_time = parse_datetime(aoi["metadata"]["event"]["time"])
        #now determine start/end times
        #see if starttime and endtime are part of the aoi metadata
        met_start, met_end = parse_start_end(aoi, event_time=event_time)
        if met_start != None: start_time = met_start
        if met_end != None: end_time = met_end
        #set priority, the most nested being the one passed
        priority = 0 #defaults to 0
        if "priority" in aoi.keys():
            priority = aoi["priority"]
        if "metadata" in aoi.keys() and "priority" in aoi["metadata"].keys():
            priority = aoi["metadata"]["priority"]
        #for each query within the aoi
        if not ("metadata" in aoi.keys() and "query" in aoi["metadata"].keys()): return None #exit if no query fields exist
        for qtype in aoi["metadata"]["query"].keys():
            #determine endpoint, skip if it does not match the qquery input endpoint
            if qtype != input_qtype:
                continue
            #set the query to run
            query = aoi["metadata"]["query"][qtype]
            #determine priority
            if "priority" in query.keys():
                priority = query["priority"]
            #parse event time for each query, if given
            query_start, query_end = parse_start_end(query, event_time=event_time)
            if query_start != None:
                #make sure the query start time is within the start/end window (if specified in aoi metadata)
                if met_start != None and convert_to_dt(query_start) < convert_to_dt(met_start):
                    #the start time in the query is before the metadata window
                    start_time = met_start
                elif met_end != None and convert_to_dt(query_start) > convert_to_dt(met_end):
                    #start of the query window is after the given metadata window
                    return None
                else:
                    #start time is between the metdata start/end window (or the window doesn't exist)
                    start_time = query_start

            if query_end != None:
                #make sure the end time is within the start/end metadata window
                if met_end != None and convert_to_dt(query_end) < convert_to_dt(met_end) and convert_to_dt(start_time) < convert_to_dt(query_end):
                    #the end time in the query is in the metadata window
                    end_time = query_end 
                elif met_end != None and convert_to_dt(query_end) > convert_to_dt(met_end):
                    #the end time in the query is after the metadata window
                    end_time = met_end
                else:
                    end_time = query_end
            
            #determine products to query for within each endpoint
            if "products" not in aoi["metadata"]["query"][qtype]: continue
            products = aoi["metadata"]["query"][qtype]["products"]
            tags = []
            if "tag" in aoi["metadata"].keys():
                tags.append(aoi["metadata"]["tag"])
            if qtype in aoi["metadata"].keys() and "tag" in aoi["metadata"][qtype].keys():
            	for tag in tags:
                    tags.append(aoi["metadata"][qtype]["tag"])

            # parses dns comma seperated string to array
            dns_list = [x.strip() for x in dns_list_str.split(',')]

            #fill parameters
            params["starttime"] = start_time
            params["endtime"] = end_time
            params["priority"] = priority
            params["products"] = products
            params["tag"] = tags
            params["dns_list"] = dns_list
            return params


        return None


    def stampKeyname(self,aoi,qtype):
        '''
        Get the timestamp keyname
        @param aoi: area of interest
        @param qtype: query type
        @return: timestamp keyname
        '''
        return aoi["id"] + "-" + qtype +"-last_query"
    def saveStamp(self,stamp,key):
        '''
        Save the query time for later use
        @param stamp: timestamp to save in key
        @param key: name of the key to set
        '''
        global POOL
        if POOL is None:
            POOL = ConnectionPool.from_url(REDIS_URL)
        r = StrictRedis(connection_pool=POOL)
        r.set(key,stamp)
    def loadStamp(self,key):
        '''
        Load the query time for this key
        @param key: key to get stamp for
        @return: time of last query, as string
        '''
        global POOL
        if POOL is None:
            POOL = ConnectionPool.from_url(REDIS_URL)
        r = StrictRedis(connection_pool=POOL)
        last = r.get(key)
        return last

class UnsupportedQueryTypeException(Exception):
    '''
    Thrown when a subclass handling the submitted type of query cannot be found
    '''
    pass
class QueryBadResponseException(Exception):
    '''
    Thrown when a query fails
    '''
    pass

def parse_datetime(dt_string, event_string=None):
    '''
    Parses the input string and determines the proper datetime to return
    @params dt_string: string from aoi, either UTC time or in a
    event +/- X days or now +- X days format
    @event_string: an optional event time string, the datetime returned is 
    calculated relative to that event time with or without an offset.
    only used if dt_string matches event_reg expression
    @return: datetime string in proper format, None if there are no matches
    '''    
    #datetime regs
    dt_reg = re.compile("(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")
    event_reg_rel = re.compile("event.*?([+-])\s*?([\d*\.]+)")
    event_reg = re.compile("(event)")
    now_reg = re.compile("(now)")
    now_reg_rel = re.compile("now\s*?([+-])\s*?([\d*\.]+)")
    #if input string is UTC time
    if dt_reg.match(dt_string):
        y,m,d,h,mn,sec = [int(i) for i in  list(re.findall(dt_reg, dt_string)[0])]
        dt = datetime.datetime(y,m,d,h,mn,sec).strftime("%Y-%m-%dT%H:%M:%S")
	return dt
    #if relative to now
    if now_reg_rel.match(dt_string):
        r = re.findall(now_reg_rel, dt_string)[0]
        t = datetime.datetime.utcnow()
        p = r[0]
        offset = float(r[1])
        if p == '+':
            return (t + datetime.timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")
        else:
            return (t - datetime.timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")
    #if is now string
    if now_reg.match(dt_string):
        dt = datetime.datetime.utcnow()
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    #is relative to an event
    if (event_string == None or not dt_reg.match(event_string)):
	#if the event string is not given or does not match datetime
        return None
    #determine the event datetime
    y,m,d,h,mn,sec = [int(i) for i in  list(re.findall(dt_reg, event_string)[0])]
    event_dt = datetime.datetime(y,m,d,h,mn,sec)
    if event_reg_rel.match(dt_string):
       r = re.findall(event_reg_rel, dt_string)[0]
       p = r[0]
       offset = float(r[1])
       if p == '+':
           return (event_dt + datetime.timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S")
       else:
           return (event_dt - datetime.timedelta(days=offset)).strftime("%Y-%m-%dT%H:%M:%S") 
    if event_reg.match(dt_string):
        return event_dt.strftime("%Y-%m-%dT%H:%M:%S")
    return None

def convert_to_dt(timestring1):
    '''Returns the datetime string YYYY-MM-DDTHH:mm:SS as a datetime object'''
    dt_reg = re.compile("(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")
    y,m,d,h,mn,sec = [int(i) for i in list(re.findall(dt_reg, timestring1)[0])]
    return datetime.datetime(y,m,d,h,mn,sec)


def parse_start_end(json_dict, event_time=None):
    '''
    Parses the input dict for temporal values. If they exist, determines proper starttime 
    and endtime strings, and returns those as a tuple. If start or endtime values do not exist,
    returns None for one or both values instead of the string.
    @params json_dict: a dict which may contain temporal starttime/endtime strings
    event_time: is an optional string which an event time may be passed
    @return: tuple containing strings for starttime, endtime, or none if none exist
    '''
    start_time = None
    end_time = None
    if "temporal" in json_dict.keys():
        return parse_start_end(json_dict["temporal"])
    #determine if there is an event time
    if ("event" in json_dict.keys() and "time" in json_dict["event"].keys()):
        event_time = parse_datetime(json_dict["event"]["time"])
    #determine start time
    if "starttime" in json_dict.keys():
        start_time = parse_datetime(json_dict["starttime"], event_string=event_time)
    #determine end time
    if "endtime" in json_dict.keys():
        end_time = parse_datetime(json_dict["endtime"], event_string=event_time)
    return (start_time, end_time)

def determine_if_expired_query(dt_string):
    '''
    Takes the input string, parses it for a utc datetime, then compares it to the current
    datetime. If the input datetime is before the current time, returns True. Else returns False
    @params dt string: input string in dt format YYYY-MM-DDTHH:mm:SS
    @return: True or False. If the string doesn't match, returns True
    '''
    dt_reg = re.compile("(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")
    if not dt_reg.match(dt_string):
        return True
    y,m,d,h,mn,sec = [int(i) for i in list(re.findall(dt_reg, dt_string)[0])]
    dt = datetime.datetime(y,m,d,h,mn,sec)
    current_t = datetime.datetime.utcnow()
    if dt < current_t:
        return True #if the given time is before the current time
    return False

def parser():
    '''
    Construct a parser to parse arguments
    @return argparse parser
    '''
    parse = argparse.ArgumentParser(description="Downloads products from https://scihub.esa.int/dhus")
    parse.add_argument("-r","--region", required=True, help="Region to submit the query for", dest="region")
    parse.add_argument("-t","--query-type", required=True, help="Query type to find correct query handler", dest="qtype")
    parse.add_argument("--tag", help="PGE docker image tag (release, version, or branch) to propagate", required=False)
    parse.add_argument("--dns_list", help="List of DNS to use as endpoint for this query, comma separated")

    return parse
    
if __name__ == "__main__":
    ''' Main program for downloading  '''
    args = parser().parse_args()
    cfg = config()
    # Detect region
    region = None

    #skip to the aoi we want
    for aoi in get_aois(cfg):
        if aoi["id"] == args.region:
            region = aoi
            break
    if region is None:
        print("Error: Failed to find appropriate aoi.",file=sys.stderr)
        exit(-1)

    try:
        print("Finding handler: {0}".format(args.qtype))
        handler = AbstractQuery.getQueryHandler(args.qtype)
        handler.run(aoi, args.qtype, args.dns_list, args.tag)
        #a = AbstractQuery()
        #a.run(aoi)
    except Exception as e:
        with open('_alt_error.txt', 'a') as f:
            f.write("%s\n" % str(e))
        with open('_alt_traceback.txt', 'a') as f:
            f.write("%s\n" % traceback.format_exc())
        raise
