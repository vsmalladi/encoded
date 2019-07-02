#!/bin/bash
# Ex) $./create-wal-e-creds.sh /path/to/creds/wale-backups-write-last-pg93

# Args
creds_dir="$1"

# Make sure slash is at the end of path
#  wal-e may or may not care about this.
length=${#creds_dir}
length=$((length - 1))
if ! [ "${creds_dir:$length:1}" == "/" ]; then
  creds_dir="$creds_dir/"
fi
creds="$creds_dir""credentials"

# Remove output files
rm "$creds_dir"'AWS_'*
if [ $? -gt 0 ]; then
    echo -e 'Failure okay on remove.  This is a clean up step.\n'
fi

# Get values
id=$(grep 'aws_access_key_id' $creds | sed 's/^.*=//')
secret=$(grep 'aws_secret_access_key' $creds | sed 's/^.*=//')
region='us-west-2'

# Remove spaces
id="$(echo -e "${id}" | tr -d '[:space:]')"
secret="$(echo -e "${secret}" | tr -d '[:space:]')"
region="$(echo -e "${region}" | tr -d '[:space:]')"

# Create output files with no new line character
dest_id="$creds_dir/AWS_ACCESS_KEY_ID"
dest_secret="$creds_dir/AWS_SECRET_ACCESS_KEY"
dest_region="$creds_dir/AWS_REGION"
echo -n "$id" >> "$dest_id"
echo -n "$secret" >> "$dest_secret"
echo -n "$region" >> "$dest_region"
echo -e '\n'
ls -l $creds_dir
