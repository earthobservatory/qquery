#!/bin/bash

# Pulls in ARIA repos outside qquery
scihub_url="https://github.com/hysds/scihub.git"
asf_url="https://github.com/hysds/asf-query.git"
unavco_url="https://github.com/hysds/unavco-query.git"
apihub_url="https://github.com/hysds/apihub.git"
# revert back later
git clone $scihub_url -b "chin_test" "scihub"
# git clone $scihub_url "scihub"
git clone $asf_url "asf"
git clone $unavco_url "unavco"
git clone $apihub_url "apihub"
