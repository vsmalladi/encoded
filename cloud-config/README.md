Organization deployment configuration and build files
=====================================================


## Summary
#### Templates are assembled into deployment yamls with ./template-parts
    # Standard
    Demo/QA Demo: app-es-pg-template.yml
    Cluster Frontend: app-pg-template.yml
    Cluster Elasticsearch: es-nodes-template.yml
    # Non Standard
    Instance with remote pg: app-es-template.yml
    Instance with remote pg/es: app-template.yml
#### Directories:
    template-parts: Pieces of the templates
    run-scripts: Shell install scripts. Usually called from runcmd_* template parts but can also be 
        used directly in a template.
    configs: Configuration files used in run-scripts
    built-ymls: Saved, assembled templates.  Still contains run variables to be filled in.
#### Other
    create-ami.py: Helpers script to create amis in AWS


## Examples with bin/deploy
    The deploy script will assembled a template based on input args
    Demo: No args will use a demo

#### QA/Developmnet Demo: app-es-pg-template
    $ bin/deploy --dry-run
    # Deploying app-es-pg
    # $ bin/deploy --dry-run
    # run_args: dict_keys(['count', 'iam_role', 'master_user_data', 'user_data', 'security_groups', 'key-pair-name'])
    # instances_tag_data {'branch': 'branch-name', 'commit': 'commit-sha', 
        'short_name': 'encd-####', 'name': 'encd-####-commit-sha', 'username': 'your-name'}
    # is_tag: False, is_branch: True
    # Dry Run

    bin/deploy


#### Demo Cluster: es-nodes-template.yml and app-pg-template
    $ bin/deploy --dry-run --cluster-name somename --es-elect
    # Deploying es-nodes
    # $ bin/deploy --dry-run --cluster-name somename --es-elect

    $ bin/deploy --dry-run --cluster-name somename --es-ip 1.2.3.4
    # Deploying app-pg
    # $ bin/deploy --dry-run --cluster-name somename --es-ip 1.2.3.4


# Deploy with ubuntu 18 base ami
    ```
    Demo
    $ bin/deploy -n test-demo --full-build
        "cycle_started": "2020-04-21T22:19:47.923214",
        "indexed": 1392520,
        "cycle_took": "3:31:02.360139"
    
    Demo Cluster
    $ bin/deploy --cluster-name test-wait --full-build --es-wait
    used by Frontend with postgres
    $ bin/deploy --cluster-name test-wait --full-build --es-ip a.b.c.d 
    ```

# Build and save a cloud config yml
    ```
    Demo
    $ bin/deploy --save-config-name 20200421 
   
    ES Node - wait
    $ bin/deploy --save-config-name 20200421 --es-wait --cluster-name some-name

    ES Node - elect
    $ bin/deploy --save-config-name 20200421 --es-elect --cluster-name some-name
    
    Frontend with postgres
    $ bin/deploy --save-config-name 20200421 --es-ip a.b.c.d --cluster-name some-name
    ```

# Deploy with prebuilt cloud config yml
    ```
    Demo
    $ bin/deploy -n test-demo-prebuilt --use-prebuilt-config 20200421-demo --full-build
   
    ES Node - wait
    $ bin/deploy --save-config-name 20200421 --es-wait --cluster-name some-name

    ES Node - elect
    $ bin/deploy --save-config-name 20200421 --es-elect --cluster-name some-name
    
    Frontend with postgres
    $ bin/deploy --save-config-name 20200421 --es-ip a.b.c.d --cluster-name some-name
    ```

# TBD
## Build encoded AMIs
## Deploy demo
## Deploy cluster

## From remote pg demo
### Deplot a demo with open postgres port
    ```
    export branch_name='ENCD-5216-deploy-demo-pointing-at-pg'
    bin/deploy -b $branch_name -n 5216-pg-open --pg-open --full-build
    ```

### Deploy a demo with open postgres port
    ```
    export branch_name='ENCD-5216-deploy-demo-pointing-at-pg'
    export pg_ip='172.31.20.118'
    # remote postgres ip will be used for --es-ip 'ignored-with-pg-ip'
    bin/deploy -b $branch_name -n 5216-pg-remote --pg-ip $pg_ip --full-build
    ```

## From remote es demo
### Deploy es cluster
    ```
    export branch_name='5212-deploy-demo-pointing-at-es-cluster'
    export cluster_name='5212-demo-es'
    bin/deploy -b $branch_name --cluster-name $cluster_name --es-wait
    # outputs: '--es-ip 172.31.23.141'
    ```

### Deploy a frontend to index the demeo
    ```
    export branch_name='5212-deploy-demo-pointing-at-es-cluster'
    export cluster_name='5212-demo-es'
    export es_ip='172.31.23.141'
    bin/deploy -b $branch_name --cluster-name $cluster_name --es-ip $es_ip
    ```

### Deploy new frontend at es ip with its own db at the current snapshot.
    ```
    export branch_name='5212-deploy-demo-pointing-at-es-cluster'
    export es_ip='172.31.23.141'
    bin/deploy -b $branch_name -n 5121-test-demo --es-ip $es_ip --full-build
    ```


