#!/bin/bash
# Setup postgres 11,
#   install wal-e,
#   run backup fetch
# postgres user
# apt deps:
#   daemontools
#   postgresql
#   postgresql-contrib
#   python3.4-venv:w
#   lzop # wal-e

standby_mode="$1"
ROLE="$2"
WALE_S3_PREFIX="$3"

AWS_CREDS_DIR='/var/lib/postgresql/.aws'
AWS_PROFILE='write-encoded-backups-dev'

PG_CONF_DEST='/etc/postgresql/11/main'
PG_CONF_SRC='/home/ubuntu/encoded/cloud-config/deploy-run-scripts/conf-pg11'
PG_DATA='/var/lib/postgresql/11/main'

WALE_DIR='/opt/pg-wal-e'
WALE_VENV="$WALE_DIR/.py343-wal-e"
WALE_BIN="$WALE_VENV/bin"
WALE_REQS='/home/ubuntu/encoded/wal-e-requirements-py3.txt'
WALE_ENV='/etc/wal-e.d/env'


function copy_with_permission {
    src_file="$1/$3"
    dest_file="$2/$3"
    sudo -u root cp "$src_file" "$dest_file"
    sudo -u root chown postgres:postgres "$dest_file"
}


function append_with_user {
  line="$1"
  user="$2"
  dest="$3"
  echo "$line" | sudo -u $user tee -a $dest
}


# Copy pg confs to pg conf dir
for filename in 'custom.conf' 'demo.conf' 'master.conf' 'recovery.conf' ; do
    copy_with_permission "$PG_CONF_SRC" "$PG_CONF_DEST" "$filename"
done

# Update Confs
##master.conf: TODO: Only production needs wal-e push ability? Move to ROLE='candidate'?"
wale_push_cmd="archive_command = '$WALE_BIN/envdir $WALE_ENV $WALE_BIN/wal-e --s3-prefix=$WALE_S3_PREFIX wal-push \"%p\"'"
append_with_user "$wale_push_cmd" 'postgres' "$PG_CONF_DEST/master.conf"
##recovery.conf
wale_fetch_cmd="restore_command = '$WALE_BIN/envdir $WALE_ENV $WALE_BIN/wal-e --aws-instance-profile --s3-prefix=$WALE_S3_PREFIX wal-fetch \"%f\" \"%p\"'"
standby_mode_cmd="standby_mode = $standby_mode"
append_with_user "$wale_fetch_cmd" 'postgres' "$PG_CONF_DEST/recovery.conf"
append_with_user "$standby_mode_cmd" 'postgres' "$PG_CONF_DEST/recovery.conf"
##postgresql.conf
include_custom="include 'custom.conf'"
append_with_user "$include_custom" 'postgres' "$PG_CONF_DEST/postgresql.conf"
if [ "$ROLE" == 'candidate' ]; then
    echo 'Candidate'
else
  include_demo="include 'demo.conf'"
  append_with_user "$include_demo" 'postgres' "$PG_CONF_DEST/postgresql.conf"
fi
##WALE_S3_PREFIX
include_custom="include 'custom.conf'"
append_with_user "$WALE_S3_PREFIX" 'root' "$PG_CONF_DEST/wale_s3_prefix"

# Create db prior to wal-e backup fetch
sudo -u postgres createuser encoded
sudo -u postgres createdb --owner=encoded encoded

# Setup wal-e aws environment
sudo -u postgres /usr/bin/aws s3 cp --region=us-west-2 --recursive s3://encoded-conf-prod/.aws "$AWS_CREDS_DIR"
sudo -u root mkdir -p "$WALE_ENV"
sudo -u root chown postgres:postgres "$WALE_ENV"
for filename in 'AWS_ACCESS_KEY_ID' 'AWS_SECRET_ACCESS_KEY' 'AWS_REGION'; do
    copy_with_permission "$AWS_CREDS_DIR" "$WALE_ENV" "$filename"
done
copy_with_permission "$PG_CONF_DEST" "$WALE_ENV" 'WALE_S3_PREFIX'

# Install wal-e
sudo -u root rm -r "$WALE_DIR"
sudo -u root mkdir -p "$WALE_DIR"
sudo -u root chown postgres:postgres "$WALE_DIR"
sudo -u root cp "$WALE_REQS" "$WALE_DIR/wal-e-requirements.txt"
sudo -u root chown postgres:postgres "$WALE_DIR/wal-e-requirements.txt"
sudo -H -u postgres python3 -m venv "$WALE_VENV"
sudo -H -u postgres "$WALE_BIN/pip" install pip setuptools boto awscli --upgrade
sudo -H -u postgres "$WALE_BIN/pip" install -r "$WALE_DIR/wal-e-requirements.txt"
sudo -u postgres git clone https://github.com/wal-e/wal-e.git "$WALE_DIR/wal-e"
sudo -H -u postgres "$WALE_BIN/pip" install -e "$WALE_DIR/wal-e"

# Update db from wale backup
sudo -u postgres pg_ctlcluster 11 main stop
sudo -u postgres "$WALE_BIN/envdir" "$WALE_ENV" "$WALE_BIN/wal-e" --aws-instance-profile --s3-prefix="$WALE_S3_PREFIX" backup-fetch "$PG_DATA" LATEST

# Set db to recoery mode:
#  TODO: backup-fetch doesnot use recovery(wale-fetch) like
# backup-push uses wal-push?
sudo -u postgres ln -s "$PG_CONF_DEST/recovery.conf" "$PG_DATA/"

# Restart db to update conf
sudo -u postgres pg_ctlcluster 11 main start

# Wait for postgres
psql_cnt=0
until sudo -u postgres psql postgres -c ""; do
    psql_cnt=$((psql_cnt+1))
    sleep 10;
    if [ $psql_cnt -gt 6 ]; then
        echo 'INSTALL FAILURE(pg11-install.sh): Postgres did not restart'
        exit 123
    fi
done
