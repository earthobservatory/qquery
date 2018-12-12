FROM hysds/pge-base

MAINTAINER jlinick "Justin.P.Linick@jpl.nasa.gov"
LABEL description="qquery base image"

ARG git_oauth_token
ARG id
ARG gid

#Change UID and GID from build
#USER root
#RUN set -ex && \
#  usermod -u ${id} ops && \
#  groupmod -g ${gid} ops && \
#  chown -R ops:ops /home/ops/ /data && \
#  usermod -g ${gid} ops
 
USER ops
# copy config
# COPY .aws /home/ops/.aws
# COPY .netrc /home/ops/.netrc
# COPY verdi/etc/datasets.json /home/ops/verdi/etc/datasets.json

# copy packages
COPY . /home/ops/verdi/ops/qquery
RUN set -ex \
 && source /home/ops/verdi/bin/activate \
 && sudo chown -R ops:ops /home/ops/verdi/ops/qquery \
 && mv /home/ops/verdi/ops/qquery/scihub /home/ops/verdi/ops/scihub \
 && mv /home/ops/verdi/ops/qquery/unavco /home/ops/verdi/ops/unavco \
 && mv /home/ops/verdi/ops/qquery/asf /home/ops/verdi/ops/asf \
 && mv /home/ops/verdi/ops/qquery/apihub /home/ops/verdi/ops/apihub \
 && cd /home/ops/verdi/ops/qquery \
 && pip install -e . \
 && cd /home/ops/verdi/ops/scihub \
 && pip install -e . \
 && cd /home/ops/verdi/ops/unavco \
 && pip install -e . \
 && cd /home/ops/verdi/ops/asf \
 && pip install -e . \
 && cd /home/ops/verdi/ops/apihub \
 && pip install -e .

WORKDIR /home/ops
CMD ["/bin/bash", "--login"]
