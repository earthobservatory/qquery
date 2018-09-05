#!/usr/bin/env bash

# wrapper for qquery query.py

CODE_DIR=$(dirname "${BASH_SOURCE}")

#validate input args
if [ -z "${1}" ] 
    then
    echo "No aoi specified"
    exit 1
fi
if [ -z "${2}" ] 
    then
    echo "No query endpoint specified"
    exit 1
fi
if [ -z "${3}" ] 
    then
    echo "No sling release version specified"
    exit 1
fi

if [ -z "${4}" ]
    then
    ${CODE_DIR}/query.py --region ${1} --query_endpoint ${2} --tag ${3}
else
    ${CODE_DIR}/query.py --region ${1} --query_endpoint ${2} --tag ${3} --dns_alias ${4}
fi