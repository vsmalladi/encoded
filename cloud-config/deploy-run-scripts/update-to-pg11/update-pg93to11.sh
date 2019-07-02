#!/bin/bash
# Upgrade encoded postgres 9.3 database to postgres 11
aws_profile="$1"
run_mode="$2"

aws_read_credentials='/home/ubuntu/aws-postgres-creds'
aws_write_credentials='/var/lib/postgresql/.aws'
s3_url='s3://encoded-backups-prod'
backup_backup="$s3_url/production-last-pg93"
# Never should be used
# current_backup="$s3_url/production"
new_backup="$s3_url/production-pg11"

echo -e "\nRun Mode: $run_mode"

if [ "$run_mode" == 'setcreds93' ]; then
  echo -e '\nSet AWS credentials for postgres user'

  echo -e "\n\tCheck $aws_read_credentials"
  if [ -d "$aws_read_credentials" ]; then
    filenames="AWS_ACCESS_KEY_ID AWS_REGION AWS_SECRET_ACCESS_KEY credentials config"
    for filename in $filenames; do
      if [ ! -f "$aws_read_credentials/$filename" ]; then
        echo -e "\t\tFailure: $aws_read_credentials/$filename does not exist."
        exit 101
      fi
    done
  else
    echo -e "\t\tFailure: Aws credentials '$aws_read_credentials' do not exist."
    exit 101
  fi

  echo -e "\n\tMove to $aws_write_credentials"
  if [ -d "$aws_write_credentials" ]; then
      sudo -u root rm -r "$aws_write_credentials"
      if [ $? -ne 0 ]; then echo 'Error' && exit 101; fi
  fi
  sudo -u postgres mkdir -p "$aws_write_credentials"
  if [ $? -ne 0 ]; then echo 'Error' && exit 101; fi
  sudo -u root cp -r $aws_read_credentials/* $aws_write_credentials/
  if [ $? -ne 0 ]; then echo 'Error' && exit 101; fi
  sudo -u root chown -R postgres:postgres $aws_write_credentials
  if [ $? -ne 0 ]; then echo 'Error' && exit 101; fi
  echo -e '\nPASSED: Set AWS credentials for postgres user'
  exit 0
fi

if [ "$run_mode" == 'backup93' ]; then
  echo -e "\nBackup 9.3 to check bucket and set server state"

  echo -e "\n\tSet wale prefix: $backup_backup"
  wale_s3_prefix_path='/etc/postgresql/9.3/main/wale_s3_prefix'
  sudo -u root rm "$wale_s3_prefix_path"
  echo -n "$backup_backup"  | sudo -u root tee -a "$wale_s3_prefix_path"

  echo -e "\n\tUpdate postgres master.conf"
  master_conf_path='/etc/postgresql/9.3/main/master.conf'
  sudo -u  postgres rm /etc/postgresql/9.3/main/master.conf
  echo "archive_command = '/opt/wal-e/bin/envfile --config ~postgres/.aws/credentials --section $aws_profile --upper -- /opt/wal-e/bin/wal-e --s3-prefix=$(cat /etc/postgresql/9.3/main/wale_s3_prefix) wal-push %p'" | sudo -u postgres tee -a "$master_conf_path"

  echo -e "\n\tInclude master.conf in postgresql.conf"
  pg_conf_path='/etc/postgresql/9.3/main/postgresql.conf'
  master_conf_line="include 'master.conf'"
  echo "$master_conf_line"  | sudo -u root tee -a "$pg_conf_path"

  echo -e "\n\tPromote pg93 to allow backup"
  sudo -u postgres pg_ctlcluster 9.3 main restart -m fast
  sudo -u postgres pg_ctlcluster 9.3 main reload
  sudo -u postgres pg_ctlcluster 9.3 main promote
  if [ $? -gt 0 ]; then
    exit
  fi
  sudo service apache2 restart

  sleep_time=30
  echo -e "\n\tRunning first backup after $sleep_time second sleep"
  cmd="sudo -u postgres /opt/wal-e/bin/envfile --config ~postgres/.aws/credentials --section $aws_profile --upper -- /opt/wal-e/bin/wal-e --s3-prefix=$(cat /etc/postgresql/9.3/main/wale_s3_prefix) backup-push /var/lib/postgresql/9.3/main"
  echo -e "\t Recovery should be false on _indexer url"
  echo -e "\t If the command fails then troubleshoot with..."
  echo -e "$cmd"
  echo -e '\nSleeping now'
  sleep $sleep_time
  eval "$cmd"
  exit 0
fi

if [ "$run_mode" == 'install11' ]; then
  echo -e "\nInstall postgres 11"

  echo -e '\n\tdeps...'
  sudo apt-get install -y libreadline-dev

  echo - '\n\tdownload...'
  pg11_name='postgresql-11.2'
  pg11_dl="https://ftp.postgresql.org/pub/source/v11.2/$pg11_name.tar.gz"
  pg11_dl_loc="/var/lib/postgresql/$pg11_name.tar.gz"
  pg11_untar_loc="/var/lib/postgresql"
  sudo -u postgres curl -o "$pg11_dl_loc" "$pg11_dl"
  sudo -u postgres tar xvzf $pg11_dl_loc -C $pg11_untar_loc

  echo -e "\n\tinstall: $pg11_untar_loc"
  cd "$pg11_untar_loc/$pg11_name"
  sudo -u postgres ./configure
  sudo -u postgres make
  sudo -u root make install
  sudo -u root mkdir /usr/local/pgsql/data
  sudo -u root chown postgres /usr/local/pgsql/data
  sudo -u postgres /usr/local/pgsql/bin/initdb -D /usr/local/pgsql/data

  echo -e '\n\tCopy 93 config and/or update...'
  sudo -u postgres cp /etc/postgresql/9.3/main/custom.conf /usr/local/pgsql/data/custom.conf
  echo "include 'custom.conf'" | sudo -u postgres tee -a /usr/local/pgsql/data/postgresql.conf
  echo "archive_command = '/opt/pg-wal-e/.py343-wal-e/bin/envdir /etc/wal-e.d/env /opt/pg-wal-e/.py343-wal-e/bin/wal-e wal-push %p'"  | sudo -u postgres tee -a /usr/local/pgsql/data/master.conf
  echo "include 'master.conf'" | sudo -u postgres tee -a /usr/local/pgsql/data/postgresql.conf

  echo -e '\n\tCreate backup script(this uses the above archive wal-e push command'
  echo "/opt/pg-wal-e/.py343-wal-e/bin/envdir /etc/wal-e.d/env /opt/pg-wal-e/.py343-wal-e/bin/wal-e backup-push /usr/local/pgsql/data"  | sudo -u postgres tee -a /var/lib/postgresql/prod-backup-postgres.sh
  sudo -u postgres chmod +x /var/lib/postgresql/prod-backup-postgres.sh
  exit 0
fi

if [ "$run_mode" == 'upgrade93to11' ]; then
  echo -e "\nUpgrade postgres 93 to 11"
  old_bin='/usr/lib/postgresql/9.3/bin'
  old_conf='/etc/postgresql/9.3/main'
  new_bin='/usr/local/pgsql/bin'
  new_conf='/usr/local/pgsql/data'

  echo -e '\n\tShutting down both postgres 93 and 11 whether running or not'
  sudo -u postgres pg_ctlcluster 9.3 main stop -m fast
  sudo -u postgres "$new_bin/pg_ctl" -D "$new_conf" stop

  echo -e '\n\tUpgrading...'
  cd ~postgres
  sudo -u postgres "$new_bin/pg_upgrade" -b "$old_bin" -d "$old_conf" -B $new_bin -D "$new_conf"

  echo -e '\n\tSwitch psql bin command symlink'
  sudo -u root mv /usr/bin/psql /usr/bin/psql.original93
  sudo -u root ln -s /usr/local/pgsql/bin/psql /usr/bin/psql

  cmd_upgrade="upgrade: $new_bin/pg_upgrade -b $old_bin -d $old_conf -B $new_bin -D $new_conf"
  cmd_start="start/stop: $new_bin/pg_ctl -D $new_conf stop"
  cmd_psql="see data: $new_bin/psql -d encoded or psql -d encoded"
  echo -e '\n\tHelper Commands: Cannot start server till installing wale34'
  echo -e "\t\t$cmd_upgrade"
  echo -e "\t\t$cmd_start"
  echo -e "\t\t$cmd_upgrade"
  echo "$cmd_upgrade" > ~/pg-helper-cmds
  echo "$cmd_start" >> ~/pg-helper-cmds
  echo "$cmd_psql" >> ~/pg-helper-cmds
  exit 0
fi

if [ "$run_mode" == 'installwale34' ]; then
  echo -e "\nInstall wal-e for python 3.4"
  sudo apt-get install python3.4-venv
  sudo -u postgres /usr/local/pgsql/bin/pg_ctl -D /usr/local/pgsql/data start
  sudo -u root mkdir /opt/pg-wal-e
  sudo -u root chown -R postgres:postgres /opt/pg-wal-e
  sudo -u root sudo -u root mkdir -p /etc/wal-e.d/env
  sudo -u root chown -R postgres:postgres /etc/wal-e.d
  sudo -u postgres cp /var/lib/postgresql/.aws/AWS_ACCESS_KEY_ID /etc/wal-e.d/env/AWS_ACCESS_KEY_ID
  sudo -u postgres cp /var/lib/postgresql/.aws/AWS_SECRET_ACCESS_KEY /etc/wal-e.d/env/AWS_SECRET_ACCESS_KEY
  sudo -u postgres cp /var/lib/postgresql/.aws/AWS_REGION /etc/wal-e.d/env/AWS_REGION
  echo -n "$new_backup" | sudo -u postgres tee -a /etc/wal-e.d/env/WALE_S3_PREFIX
  sudo -H -u postgres python3 -m venv /opt/pg-wal-e/.py343-wal-e
  sudo apt-get remove -y awscli
  sudo -H -u postgres /opt/pg-wal-e/.py343-wal-e/bin/pip install pip setuptools boto awscli --upgrade
  sudo -u root cp /home/ubuntu/encoded/wal-e-requirements-py3.txt /opt/pg-wal-e
  sudo -u root chown postgres:postgres /opt/pg-wal-e/wal-e-requirements-py3.txt
  sudo -H -u postgres /opt/pg-wal-e/.py343-wal-e/bin/pip install -r /opt/pg-wal-e/wal-e-requirements-py3.txt
  sudo -u postgres git clone https://github.com/wal-e/wal-e.git /opt/pg-wal-e/wal-e
  sudo -H -u postgres /opt/pg-wal-e/.py343-wal-e/bin/pip install -e /opt/pg-wal-e/wal-e
  sudo -u root rm -r /opt/wal-e

  echo -e '\n\tRestarting 11...'
  new_bin='/usr/local/pgsql/bin'
  new_conf='/usr/local/pgsql/data'
  sudo -u postgres "$new_bin/pg_ctl" -D "$new_conf" start

  echo -e '\n\tRun backup command'
  echo -e '\t\t$sudo su - postgres'
  echo -e '\t\t$./prod-backup-postgres.sh'
  exit 0
fi

echo 'update-pg93to11.sh: Nothing Happened!'
exit 9999
