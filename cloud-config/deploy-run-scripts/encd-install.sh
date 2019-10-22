#!/bin/bash
# Setup encoded app
# encoded user
# apt deps:

GIT_REPO="$1"
GIT_BRANCH="$2"
ROLE="$3"
ES_IP="$4"
ES_PORT="$5"
REGION_INDEX="$6"
APP_WORKERS="$7"
PG_IP="$8"
PG_URI="postgresql://$PG_IP/encoded"
if [ "$PG_IP" == 'none' ]; then
    PG_URI='postgresql:///encoded'
fi

script_name="$(basename $0)"
echo "****START-ENCD-INFO($script_name)****"
echo -e "\tGIT_REPO=$GIT_REPO"
echo -e "\tGIT_BRANCH=$GIT_BRANCH"
echo -e "\tROLE=$ROLE"
echo -e "\tES_IP=$ES_IP"
echo -e "\tES_PORT=$ES_PORT"
echo -e "\tREGION_INDEX=$REGION_INDEX"
echo -e "\tPG_IP=$PG_IP"
echo -e "\tPG_URI=$PG_URI"

encd_home='/srv/encoded'
mkdir "$encd_home"
chown encoded:encoded "$encd_home"
cd "$encd_home"
sudo -u encoded git clone "$GIT_REPO" .
sudo -u encoded git checkout -b "$GIT_BRANCH" origin/"$GIT_BRANCH"
sudo pip3 install -U zc.buildout setuptools redis
sudo -u encoded buildout bootstrap
sudo -u encoded LANG=en_US.UTF-8 bin/buildout -c "$ROLE".cfg buildout:es-ip="$ES_IP" buildout:es-port="$ES_PORT" buildout:pg-uri="$PG_URI"
sudo -u encoded mkdir /srv/encoded/.aws
sudo -u root cp /home/ubuntu/encd-aws-keys/* /srv/encoded/.aws/
sudo -u root chown -R encoded:encoded ~encoded/.aws
until sudo -u postgres psql postgres -c ""; do sleep 10; done
sudo -u encoded sh -c 'cat /dev/urandom | head -c 256 | base64 > session-secret.b64'
if [ "$PG_IP" == 'none' ]; then
    echo "ENCD-INFO($script_name): PG_IP is none. Run create mappting and index annotations."
    sudo -u encoded bin/create-mapping production.ini --app-name app
    sudo -u encoded bin/index-annotations production.ini --app-name app
fi
cp /srv/encoded/etc/logging-apache.conf /etc/apache2/conf-available/logging.conf
# Create encoded apache conf
a2conf_src_dir="$encd_home/cloud-config/deploy-run-scripts/conf-apache"
a2conf_dest_file='/etc/apache2/sites-available/encoded.conf'
sudo -u root "$a2conf_src_dir/build-conf.sh" "$REGION_INDEX" "$APP_WORKERS" "$a2conf_src_dir" "$a2conf_dest_file" "$PG_IP"
echo "****END-ENCD-INFO($script_name)****"
