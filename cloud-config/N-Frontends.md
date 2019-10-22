# N-Frontends Notes

## Working: 20191028 after rebasing per v92rc1
* build a pg/es open host demo
    * bin/deploy -n pgopenhd --pg-open
* build a client demo with es-ip and pg-ip for pgopenhd. No indexing workers in apache conf.
    * bin/deploy -n pgopencd --es-ip 172.31.28.178 --pg-ip 172.31.28.178

## Notes
### Check psql connections
select pid as process_id,
       usename as username,
       datname as database_name,
       client_addr as client_address,
       application_name,
       backend_start,
       state,
       state_change
from pg_stat_activity;

### Manual Open host
    * the security group allows 5432 access between eachother already
    * Failed: $ telnet 172.31.29.110 5432 
    * Add "listen_addresses = '*'" to postgresql.conf
    * Passed: $ telnet 172.31.29.110 5432 
    * $ sudo su - encoded
    * Failed: $ psql -h 172.31.29.110
    * Add "host encoded encoded 172.31.26.133/24 trust" to bottom of pg_hba.conf
    * Passed: $ psql -h 172.31.29.110
#### Above works but does not scale live on a prod cluster.  
    * We should fix security group and trust all connections


## Final Plan
* can we password protect post/put/patch on the primary pg node?
* Build demo-es-cluster(Skipping and just building demo)
* Build primary-frontend 
    * connecting to demo-es-cluster
    * open pg traffic to internal security group
* Build secondary-frontend
    * connecting to demo-es-cluster
    * no index worker apache threads
    * connecting to primary-frontend-postgres
