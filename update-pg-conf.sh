#!/bin/bash
run="$1"

function run {
  echo -e "\n\n$3"
  dest="/etc/postgresql/$2/main/postgresql.conf"
  cmd="scp $1 $3:~/$1"
  eval "$cmd"
  cmd="ssh $3 'sudo -u root mv ~/$1 $dest'"
  eval "$cmd"
  cmd="ssh $3 'sudo -u root chown postgres:postgres $dest'"
  eval "$cmd"
  cmd="ssh $3 'sudo -u postgres pg_ctlcluster $2 main reload'"
  eval "$cmd"
  cmd="ssh $3 'sudo service apache2 restart'"
  eval "$cmd"
  cmd="ssh $3 'tail -f /var/log/apache2/error.log'"
  eval "$cmd"
}


if [ "$run" == "93" ]; then
  host='devpg93prod.ubu'
  run 'postgresql-93.conf' '9.3' $host
  exit 0
fi

if [ "$run" == "11" ]; then
  host='3336d.ubu'
  run 'postgresql-11.conf' '11' $host
  exit 0
fi
