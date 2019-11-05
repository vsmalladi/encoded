# Read This: 
- This was last updated during the Prod Test Upgrade on 20191016
    - The first one worked with minor issues.  
        - Demos and Demo clusters were deployed with correct indexing times
    - The second one worked with some issues due to merging code
        - currently building a pg11 demo
    - The thrid one was never finished due to other issues.
- See Test Upgrade First
    - Production Upgrade/Release is only done once after a Test Upgrade
- Becareful deviating from the process
    - Do not expect this to work on a released production machine
    - Do not run a machine with the wrong credentials

## Production Upgrade/Release
    1. Current Version(vN) is running in recovery false. See https://www.encodeproject.org/_indexer -> "recovery": true
    2. Next Version(vN+1) was deployed as normal release, let indexing finish
    3. vN+1 is also recovery true: See http://v90x1-pg11update-master.production.encodedcc.org/_indexer -> "recovery": true
    4. Verify on the two urls have the same snapshot.  See each url -> "snapshot": "25450482:25450482:"
    5. **(only once)** Per release Doc: Block writes on vN
    6. Do Postgres 9.3 to 11 Upgrade Steps below on vN+1
    7. A postgres 11 backup should exist now
    8. Shut down upgrade machine, vN+1
    9. **(only once)** Merge ENCD-3336 
    10. **(only once)** Make a release vN+1.1 and deploy
    11. Test vN+1.1 
    12. Return to release doc after Block writes on vN

## Test Upgrade
    1. Do **Setps 1** in Production Upgrade/Release above
    2. Deploy Pg Upgrade Test Cluster
Cluster: bin/deploy -b v91.0 --cluster-name v91x0-pgupdater --es-wait --profile-name production
Frontend: bin/deploy -b v91.0 --cluster-name v91x0-pgupdater --profile-name production --candidate --es-ip 172.31.20.7
    3. Do **Setps 3 and 4** in Production Upgrade/Release above
    4. Do **Setps 6-8** in Production Upgrade/Release above
    3. Test Types of Deployments to check deployment/indexing at the bottom of this doc using ENCD-3336 branch
    4. Create a cluster for QA with ENCD-3336 off pg11 backup
    5. Do Production Upgrade/Release


# Postgres 9.3 to 11 Upgrade Steps

## AWS Console and Credentials
### **DO NOT TOUCH**: s3/buckets/encoded-backups-prod/production
### Clean up backup buckets: Remove all files from from not production bucket folders
    * s3/buckets/encoded-backups-prod/production-last-pg93
    * s3/buckets/encoded-backups-prod/production-pg11

### Create Creds
#### Setup credentials
    * vN+1 does not yet have credentials to write to s3/buckets/encoded-backups-prod
    * This usually happens during regular release.  In this case we need new creds
##### Make creds
    * Go to AWS console -> IAM -> wale-write-backups-prod user -> credentials
    * remove all access keys and create a new one
    * download csv to ~/Downloads
##### Save creds locally: 
    * $ mkdir ~/.aws/other/wale-write-backups-prod
    * $ cd ~/.aws/other/wale-write-backups-prod
    * $ rm all-the-files-in-here
    * $ mv ~/Downloads/credentials.csv ./credentials.csv
    * # Next two commands need branch preENCD-3336-Upgrade-postgres-11
    * $ cp ~/your-repos-dir/encoded/cloud-config/deploy-run-scripts/update-to-pg11/_examples/config ./
    * $ cp ~/your-repos-dir/encoded/cloud-config/deploy-run-scripts/update-to-pg11/_examples/credentials ./
    * Copy over the access keys to credentials file

### Create Wale creds and move to remote
#### Parse local creds into wal-e env files
    * # In another terminal     
    * $ cd ~/your-repos-dir/encoded/cloud-config/deploy-run-scripts/update-to-pg11
    * $ ./create-wal-e-creds.sh ~/.aws/other/wale-write-backups-prod
    * $ ls ~/.aws/other/wale-write-backups-prod
    * # See the AWS_* credentials files
#### Move local creds to remote: Host is v90x1m.ubu in this case
    * $ ./move-aws-creds-to-demo.sh your-host ~/.aws/other/wale-write-backups-prod
    * $ssh your-host
    * (your-host)$ ls -l ~/
    * (your-host)$ ls -l ~/aws-postgres-creds
    * # See Creds
    * # These creds need to exist here and will be moved to final location later

# On remote: (your-host) $ssh your-host
    * The same script is run a few times with different args to accomplish the update.
    * Follow the sequences and make sure they passed.
## Check setup
    * $ cd ~/encoded
    * $ git fetch origin -p
    * $ git checkout -b preENCD-3336-Upgrade-postgres-11 origin/preENCD-3336-Upgrade-postgres-11
    * $ cd ~/encoded/cloud-config/deploy-run-scripts/update-to-pg11
### Copy psql helper scripts to postgres home dir for later use
    * $ sudo su
    * $ cp psql-query-time.s* ~encoded
    * $ chown encoded:encoded ~encoded/psql-query-time.s*
    * $ ls -l ~encoded | grep psql
    * $ exit

## Sequences
### 1st seq: run mode = setcreds93 : Moves creds to correct location and double checks values
        # * # 2nd ssh session
        # * $ sudo su - postgres
        # * # Tail pg logs: should see failing restore command?
        # * $ tail -f /var/log/postgresql/postgresql-9.3-main.log
        # * # Back to origin ssh session
        # * # Turn off postgres restore filling logs - recovery false
        # * $ sudo su - postgres
        # * $ cd /etc/postgresql/9.3/main
        # * $ vi custom.conf
        # * # Edit file to archive_mode = off 
        # * $ vi custom.conf
        # * # remove the restore command
        # * $ exit
        # * $ sudo service postgresql restart
    * $ cd ~/encoded/cloud-config/deploy-run-scripts/update-to-pg11
    * $ ./update-pg93to11.sh wale-write-backups-prod setcreds93
        * 1st arg: profile name set earlier
        * 2nd arg: run mode
    * $ ls -l ~postgres/.aws
    * See the creds have been moved

### 2nd seq: run mode = backup93 : Set wal-e prefix, Set for recovery false, promote, and run backup
#### Switching vN+1 machine to recovery false: We need to switch recovery from true to false and do a backup.
    * server promotion is required.
    * Do not do this on a live/released production instance in the load balencer.
    * Wale-prefix is set in update-pg93to11.sh. Make sure backup_backup and new_backup are not production
    * AWS s3 bucket and sub-folders are hard coded in the update script
    * In aws console, go to s3/buckets/encoded-backups-prod/production-last-pg93.  Should be empty
    * Check vN+1/_indexer url.  Make sure recovery is true
#### Run Backup
        # * $ sudo su - postgres
        # * $ cd /etc/postgresql/9.3/main
        # * $ vi custom.conf
        # * # Edit file to archive_mode = on
        # * $ exit
        # * # DO NOT RESTART POSTGRES  the update-pg93to11.sh will do this
    * $ ./update-pg93to11.sh wale-write-backups-prod backup93
    * # Back up should end with 'NOTICE:  pg_stop_backup complete, all required WAL segments have been archived'
    * # any other output means failure.  Figure out the issue and restart.
    * # Verify back up in aws s3 console by deploying an instance with that wal-e s3 prefix
    * (local-pc) $ bin/deploy -b origin/dev -n lastpg93wale --wale-s3-prefix s3://encoded-backups-prod/production-last-pg93
        # Deploying demo
        # $ bin/deploy -b origin/dev -n lastpg93wale --wale-s3-prefix s3://encoded-backups-prod/production-last-pg93
        Host lastpg93wale.*
          Hostname i-01aabe51b9248c667.instance.encodedcc.org
          # https://lastpg93wale.demo.encodedcc.org
          # ssh ubuntu@i-01aabe51b9248c667.instance.encodedcc.org
    * # Check vN+1/_indexer url.  Make sure recovery is false

### 3rd seq: run mode = install11 : Download, Install postgres 11.  Copy 9.3 config to 11. Create prod backup script
    * Here we just in install pg11.  Next is the upgrade.
    * $ ./update-pg93to11.sh wale-write-backups-prod install11
    * The last step creates the ~postgres/prod-backup-postgres.sh with the yet to be installed wal-e 3.4

### 4th seq: run mode = upgrade93to11 : Shut down both pg93 and pg11, run upgrade with proper args, prints helper commands
    * $ ./update-pg93to11.sh wale-write-backups-prod upgrade93to11
    * # helper commands are save in ~/pg-helper-cmds

### 5th seq: run mode = installwale34 : start pg11, create envdir with AWS creds, create pyenv, and install reqs
    * $ ./update-pg93to11.sh wale-write-backups-prod installwale34
    * # Restarting postgress will trigger a wal-push action.  It prints out in the console after this script ends.
    * # you can see the wal push in production-pg11 s3 bucket.
    * # Kill the script after a few minutes, wal logs get printed here after server restart.
    * # We make a full back up after optimizing db
#### Check new db, may need to start pg11
    * $ sudo su - encoded
    * $ psql
    * => \dt
    * # see the tables!
    * => ctrl-d
    * $ exit
##### Optimize DB
    * $ sudo su - encoded
    * $ ./psql-query-time.sh
    * # real    0m0.136s
    * # user    0m0.000s
    * # sys     0m0.002s
    * # add output query time to test-query.json
    * # See timing at start of test-query.json
        #"Startup Cost": 597.45
        #"Total Cost": 1275.74
        #"Plan Rows": 1
        #"Plan Width": 280
        #"Actual Startup Time": 128.912
        #"Actual Total Time": 128.918
    * # See timing at end too
        #"Planning Time": 0.963
        #"Execution Time": 129.024
    * $mv test-query.json pre-vac-1-test-query.json
##### Using given postgres command
    * $ sudo su - postgres
    * $ ./analyze_new_cluster.sh 
    * $ exit
    * $ sudo su - encoded
    * $ ./psql-query-time.sh
    * # real	0m0.008s
    * # user	0m0.000s
    * # sys	0m0.002s
    * # add output query time to test-query.json
    * # See timing at start of test-query.json
        #"Startup Cost": 1.84
        #"Total Cost": 20.77
        #"Plan Rows": 1
        #"Plan Width": 1206
        #"Actual Startup Time": 0.111
        #"Actual Total Time": 0.114
    * # See timing at end too
        #"Planning Time": 1.501
        #"Execution Time": 0.207
    * $mv test-query.json given-analyze-cmd-test-query.json
##### Using psql command: SKIPPED on v91x0 test update
    * $ sudo su - encoded 
    * $ psql
    * => VACUUM (FULL, ANALYZE);
    * # should see wal-e push logs in postgres tail
    * # take 5/10 minutes
    * => crtl-d
    * $ ./psql-query-time.sh
        # real    0m0.015s
        # user    0m0.000s
        # sys     0m0.002s
    * # add output query time to test-query.json
    * # See timing at start of test-query.json
        # "Startup Cost": 1.84
        # "Total Cost": 20.63
        # "Plan Rows": 1
        # "Plan Width": 1207
        # "Actual Startup Time": 0.154
        # "Actual Total Time": 0.156
    * # See timing at end too
        # "Planning Time": 2.445
        # "Execution Time": 0.241
    * $ mv test-query.json psql-test-query.json
    * $ exit
    * $ cd ~
    * $ sudo su 
    * $ cp ~encoded/*-test-query.json ./
    * $ chown ubuntu:ubuntu *-test-query.json ./
    
#### Run a wal-e backup with the script as postgres user
    * $ sudo su - postgres
    * $ ./prod-backup-postgres.sh
    * # wait for success message
    * # NOTICE:  pg_stop_backup complete, all required WAL segments have been archived
    * # AWS s3 production-11 bucket should now have base_backups

# Back on local
## Copy test-query.json files to this branch
    * $cd your-encd-repo/cloud-config/deploy-run-scripts/update-to-pg11/test-query-results
    * $scp your-host:~/*-test-query.json ./
    * # updates names with date, add and commit
    * # push updates


# Create a demo with pg11(local-pc)
    * $ git fetch origin -p
    * $ git checkout ENCD-3336-Upgrade-postgres-11 origin/ENCD-3336-Upgrade-postgres-11
    * $ bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n testpg11 --wale-s3-prefix s3://encoded-backups-prod/production-pg11 --postgres-version 11
        # Deploying pg11-demo: rebuilt 20191008
        # $ bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n testpg11 --wale-s3-prefix s3://encoded-backups-prod/production-pg11 --postgres-version 11
        Host testpg11.*
          Hostname i-04281b339133469f2.instance.encodedcc.org
          # https://testpg11.demo.encodedcc.org
          # ssh ubuntu@i-04281b339133469f2.instance.encodedcc.org


# Types of Deployments: Did not test single head wait node/frontend

## Deployment commands: bin/deploy -b ENCD-3336-Upgrade-postgres-11

### Single Demos(sd):
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n sd-pg93 --use-prebuilt-config 20190923-pg93-demo --wale-s3-prefix s3://encoded-backups-prod/production
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n sd-pg93-last --use-prebuilt-config 20190923-pg93-demo --wale-s3-prefix s3://encoded-backups-prod/production-last-pg93
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n sd-pg11 --use-prebuilt-config 20190923-pg11-demo --wale-s3-prefix s3://encoded-backups-prod/production-pg11

### Demo Cluster(dc) Nodes:  
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n dc-pg93-data --cluster-name dc-pg93-cluster --use-prebuilt-config 20190923-es-elect-head --instance-type m5.xlarge --elasticsearch --cluster-size 5
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n dc-pg11-data --cluster-name dc-pg11-cluster --use-prebuilt-config 20190923-es-elect-head --instance-type m5.xlarge --elasticsearch --cluster-size 5
### Demo Cluster(dc) Frontend:
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n dc-pg93-master --cluster-name dc-pg93-cluster --use-prebuilt-config 20190923-pg93-frontend --wale-s3-prefix s3://encoded-backups-prod/production --instance-type c5.9xlarge --image-id ami-2133bc59 --no-es --es-ip IP
bin/deploy -b ENCD-3336-Upgrade-postgres-11 -n dc-pg11-master --postgres-version 11 --cluster-name dc-pg11-cluster --use-prebuilt-config 20190923-pg11-frontend --wale-s3-prefix s3://encoded-backups-prod/production-pg11 --instance-type c5.9xlarge --image-id ami-2133bc59 --no-es --es-ip IP


### RC Cluster(rc) Nodes: --instance-type m5.xlarge --elasticsearch --cluster-size 5 --use-prebuilt-config 20190923-es-elect-head
-n rc-pg93-data
    --cluster-name rc-pg93-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n rc-pg11-data
    --cluster-name rc-pg11-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11

### RC Cluster(rc) Frontend: --release-candidate --instance-type c5.9xlarge --image-id ami-2133bc59 --no-es --es-ip IP
-n rc-pg93-master
    --use-prebuilt-config 20190923-pg93-frontend
    --cluster-name rc-pg93-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n rc-pg11-master --postgres-version 11
    --use-prebuilt-config 20190923-pg11-frontend
    --cluster-name rc-pg11-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11


### Test Cluster(tc) Nodes: --instance-type m5.xlarge --elasticsearch --cluster-size 5 --use-prebuilt-config 20190923-es-elect-head
-n tc-pg93-test-data
    --cluster-name tc-pg93-test-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n tc-pg11-test-data
    --cluster-name tc-pg11-test-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11

### Test Cluster(tc) Frontend: --instance-type c5.9xlarge --image-id ami-2133bc59 --no-es --es-ip IP
-n tc-pg93-test-master
    --use-prebuilt-config 20190923-pg93-frontend
    --cluster-name tc-pg93-test-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n tc-pg11-test-master --postgres-version 11
    --use-prebuilt-config 20190923-pg11-frontend
    --cluster-name tc-pg11-test-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11


### Prod Cluster(pc) Nodes: --profile-name production --instance-type m5.xlarge --elasticsearch --cluster-size 5 --use-prebuilt-config 20190923-es-elect-head
-n pc-pg93-data
    --cluster-name pc-pg93-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n pc-pg11-data --postgres-version 11
    --cluster-name pc-pg11-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11

### Prod Cluster(pc) Frontend: --profile-name production --candidate --instance-type c5.9xlarge --image-id ami-2133bc59 --no-es --es-ip IP
-n pc-pg93-test-master
    --use-prebuilt-config 20190923-pg93-frontend
    --cluster-name pc-pg93-test-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production
-n pc-pg11-master --postgres-version 11
    --use-prebuilt-config 20190923-pg11-frontend
    --cluster-name pc-pg11-cluster
    --wale-s3-prefix s3://encoded-backups-prod/production-pg11
