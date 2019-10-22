#!/bin/bash
# Setup elasticsearch data node config
# root user
# apt deps:
#   java
#   elasticsearch with apt_source and key

CLUSTER_NAME="$1"
JVM_GIGS="$2"
ES_OPT_FILENAME="$3"
PG_OPEN="$4"

script_name="$(basename $0)"
echo "****START-ENCD-INFO($script_name)****"
echo -e "\tCLUSTER_NAME=$CLUSTER_NAME"
echo -e "\tJVM_GIGS=$JVM_GIGS"
echo -e "\tES_OPT_FILENAME=$ES_OPT_FILENAME"
echo -e "\tPG_OPEN=$PG_OPEN"

opts_src='/home/ubuntu/encoded/cloud-config/deploy-run-scripts/conf-es'
opts_dest='/etc/elasticsearch'


function copy_with_permission {
    src_file="$1"
    dest_file="$2"
    sudo -u root cp "$src_file" "$dest_file"
    sudo -u root chown root:elasticsearch "$dest_file"
}

function append_with_user {
  line="$1"
  user="$2"
  dest="$3"
  echo "$line" | sudo -u $user tee -a $dest
}


# jvm options
jvm_opts_filename='jvm.options'
jvm_xms='-Xms'"$JVM_GIGS"'g'
jvm_xmx='-Xmx'"$JVM_GIGS"'g'
append_with_user "$jvm_xms" ubuntu "$opts_src/$jvm_opts_filename"
append_with_user "$jvm_xmx" ubuntu "$opts_src/$jvm_opts_filename"
copy_with_permission "$opts_src/$jvm_opts_filename" "$opts_dest/$jvm_opts_filename"

# elasticsearch options
es_opts_filename="$ES_OPT_FILENAME"
if [ "$CLUSTER_NAME" == 'NONE' ]; then
    echo 'ENCD-INFO(es-install.sh): No CUSTER_NAME. Not a elasticsearch cluster'
    if [ "$PG_OPEN" == 'true' ]; then
        echo 'ENCD-INFO(es-install.sh): PG_OPEN is true. Allow remote es connections'
        open_host='network.host: 0.0.0.0'
        transpost_port='transport.tcp.port: 9299'
        append_with_user "$open_host" ubuntu "$opts_src/$es_opts_filename"
        append_with_user "$transpost_port" ubuntu "$opts_src/$es_opts_filename"
    fi
else
    # Only append a cluster name if it is not 'NONE'
    # like single demos do not have cluster names
    cluster_name="cluster.name: $CLUSTER_NAME"
    append_with_user "$cluster_name" ubuntu "$opts_src/$es_opts_filename"
fi
copy_with_permission "$opts_src/$es_opts_filename" "$opts_dest/elasticsearch.yml"

# Setup/Restart
update-rc.d elasticsearch defaults
sudo /usr/share/elasticsearch/bin/elasticsearch-plugin install discovery-ec2
service elasticsearch restart
echo "****END-ENCD-INFO($script_name)****"
