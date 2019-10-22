#!/bin/bash
# Setup cloudwatchmon
# build user
# apt deps:
#       virtualenv

script_name="$(basename $0)"
echo "****START-ENCD-INFO($script_name)****"
DEPLOY_SCRIPT_DIR='cloud-config/deploy-run-scripts'
mkdir /opt/cloudwatchmon
chown build:build /opt/cloudwatchmon
cd /opt/cloudwatchmon
cp ~ubuntu/encoded/$DEPLOY_SCRIPT_DIR/cloudwatchmon-requirements.txt cloudwatchmon-requirements.txt
sudo -u build virtualenv --python=python2.7 ./
sudo -u build /opt/cloudwatchmon/bin/pip install -r cloudwatchmon-requirements.txt
echo "****END-ENCD-INFO($script_name)****"
