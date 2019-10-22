#!/bin/bash
# #
# This will build the encoded.conf for apache in dest_file location
# - On a demo the encd.install.sh script sets the source and destintion
# - This sript can be tested in the build-conf.sh script directory by running 
#       $./build-conf.sh True 6 or $./build-conf.sh False 3
#  without any args.  Current directory is assumed.
# # 

REGION_INDEX="$1"
APP_WORKERS="$2"
src_dir="$3"
if [ -z "$src_dir" ]; then
    src_dir="./"
fi
dest_file="$4"
if [ -z "$dest_file" ]; then
    dest_file="$src_dir/encoded.conf"
fi
PG_IP="$5"

script_name="$(basename $0)"
echo "****START-ENCD-INFO($script_name) inside encd-install.sh****"
echo -e "\tREGION_INDEX=$REGION_INDEX"
echo -e "\tAPP_WORKERS=$APP_WORKERS"
echo -e "\tsrc_dir=$src_dir"
echo -e "\tdest_file=$dest_file"
echo -e "\tPG_IP=$PG_IP"

# Top
cat "$src_dir/head.conf" > "$dest_file"
sed "s/APP_WORKERS/$APP_WORKERS/" <  "$src_dir/app.conf" >> "$dest_file"

# indexer processes
if [ "$PG_IP" == 'none' ]; then
    echo "ENCD-INFO($script_name): PG_IP is none. Add index and vis procs"
    cat "$src_dir/indexer-proc.conf" >> "$dest_file"
    cat "$src_dir/vis-indexer-proc.conf" >> "$dest_file"
fi
if [ "$REGION_INDEX" == "True" ]; then
    cat "$src_dir/region-indexer-proc.conf" >> "$dest_file"
fi

# Some vars
cat "$src_dir/some-vars.conf" >> "$dest_file"

# indexer directory permissions
cat "$src_dir/indexer-dir-permission.conf" >> "$dest_file"
cat "$src_dir/vis-indexer-dir-permission.conf" >> "$dest_file"
if [ "$REGION_INDEX" == "True" ]; then
    cat "$src_dir/region-indexer-dir-permission.conf" >> "$dest_file"
fi

# the rest
cat "$src_dir/the-rest.conf" >> "$dest_file"
echo "****END-ENCD-INFO($script_name) inside encd-install.sh****"
