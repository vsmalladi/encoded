Organization deployment configuration and build files
=====================================================


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

