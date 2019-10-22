#!/bin/bash
# Run batchupgrade
# encoded user
# apt deps:

env_ini=$1
batchsize=$2
chunksize=$3
processes=$4
maxtasksperchild=$5
ROLE="$6"
PG_IP="$7"

script_name="$(basename $0)"
echo "****START-ENCD-INFO($script_name)****"
echo -e "\tenv_ini=$env_ini"
echo -e "\tbatchsize=$batchsize"
echo -e "\tchunksize=$chunksize"
echo -e "\tprocesses=$processes"
echo -e "\tmaxtasksperchild=$maxtasksperchild"
echo -e "\tROLE=$ROLE"
echo -e "\tPG_IP=$PG_IP"

if [ "$PG_IP" == 'none' ]; then
    echo 'ENCD-INFO(bactchupgrade-run.sh): PG_IP is none. Skip batch upgrades'
    exit 0
fi

if [ "%(ROLE)s" = "demo" ]; then
    sudo -i -u encoded bin/batchupgrade $env_ini --app-name app --batchsize $batchsize --chunksize $chunksize --processes $processes --maxtasksperchild $maxtasksperchild
fi
echo "****END-ENCD-INFO($script_name)****"
