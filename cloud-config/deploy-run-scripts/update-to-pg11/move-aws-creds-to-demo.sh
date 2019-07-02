#!/bin/bash
# Ex) $./move-aws-creds-to-demo.sh 3336.ubu /path/to/creds/wale-backups-write-last-pg93

# Args
host="$1"
aws_creds_dir="$2"

# Try to delete previous creds
ssh $host 'rm -r ~/aws-postgres-creds && exit'
if [ $? -gt 0 ]; then
    echo -e 'Failure okay on remove.  This is a clean up step.\n'
fi

# Move creds dir to remote
cmd="scp -r $aws_creds_dir $host:~/aws-postgres-creds"
eval "$cmd"
