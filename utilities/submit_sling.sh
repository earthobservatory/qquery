#!/bin/bash

set -x
echo `pwd` 1>&2

#check input args
if [ -z "$1" ] 
then
    echo "filename specified"
    exit 1
fi
if [ -z "$2" ] 
then
    echo "No download_url specified"
    exit 1
fi
if [ -z "$3" ] 
then
    echo "No queue specified"
    exit 1
fi
if [ -z "$4" ] 
then
    echo "No release_version specified"
    exit 1
fi
if [ -z "$5" ] 
then
    echo "No priority specified"
    exit 1
fi
if [ -z "$6" ] 
then
    echo "No dedup specified"
    exit 1
fi
if [ '' = "$7" ]
then
    tagstring=''
else
	tagstring="--tags "${7}
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
${DIR}/submit_sling.py --filename "${1}" --download_url "${2}" --queue "${3}" --release "${4}" --priority "${5}" --dedup "${6}" ${tagstring}
