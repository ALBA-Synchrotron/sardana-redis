## Sardana Redis BlissData 1.0 Recorder

Proof of Concept to use [BlissData 1.0](https://bliss.gitlab-pages.esrf.fr/bliss/master/blissdata/intro.html) in a [Sardana](https://gitlab.com/sardana-org/sardana) recorder to publish data on a Redis DB. It stores the scan data (only counters for now) and can be used with the Nexus Writer provided in [Bliss](https://bliss.gitlab-pages.esrf.fr/bliss/master/) to write nexus files.

### Installation
The minimum requirements to test the Sardana Redis BlissData 1.0 Recorder are [Sardana](https://gitlab.com/sardana-org/sardana), [Blissdata 1.0](https://gitlab.esrf.fr/bliss/bliss/-/tree/blissdata/1.0.2/blissdata?ref_type=tags) and a Redis database.

These requirements que be installed in a conda environment:

```bash
# Select conda channels
conda config --env --add channels conda-forge
conda config --env --append channels esrf-bcu

# Create conda environment
conda create -n sardana_redis python=3.9
conda activate sardana_redis

# Install Redis
conda install "redis-server>=7" "redisearch>=2.6.5" "redisjson>=2.4.5"

# Install BlissData 1.0
conda install blissdata=1.0.2

# Install Sardana
conda install sardana=3.4.3
```

For details on installing and running a Sardana server please follow the instructions [here](https://sardana-controls.org/users/getting_started/index.html)

In the [Bliss](https://gitlab.esrf.fr/bliss/) repository there are scripts to launch the Redis database, the Nexus Writer, a Scan Monitor and Flint without the need of a running Bliss Beacon Server. A fork with some minor changes on this scripts and with the current working version for the Sardana Redis Recorder can be used to start these services:

```bash
# Clone the repo
$ git clone https://gitlab.com/alba-synchrotron/controls-section/bliss.git

# Go to the scripts folder
$ cd bliss/scripts/scanning/withoutbliss
```

Then, from this folder we can launch:
1) the Redis server (default in localhost:6379):

   ```bash
   $ ./startredis.sh
   ```

2) The scan monitor:
   ```bash
   $ ./startmonitor.py --redis redis://localhost:6379 --session test_session
   ```

4) Nexus Writer service (it needs to be installed first):
   ```bash
   $ conda install blisswriter=1.0.1
   $ ./startwriter.py --redis redis://localhost:6379 --session test_session --name nexus  # name is the writer name, should match the scan_info['data_writer'] to write the scan
   ```

4) Flint. Requires Bliss to be installed in the same conda environment. Follow info from [here](https://bliss.gitlab-pages.esrf.fr/bliss/master/installation.html) and then execute the script passing as argument the session name (default=test_session):
   ```bash
   $ ./startflint.sh test_session
   ```

Finally, install the sardana_redis plugin that contains the recorder from the setup.py file.

```bash
# Clone the repo
$ git clone https://github.com/ALBA-Synchrotron/sardana-redis.git
$ pip install ./sardana-redis
```

and edit the Sardana Macroserver RecorderPath property to point to the recorder folder where the plugin has been installed (if the instructions have been followed, it should be: `$CONDA_PREFIX/lib/python3.9/site-packages/sardana_redis/recorder/`)


### Usage
The recorder can be activated by setting it as a DataRecorder from spock with the command `senv DataRecorder "RedisBlissRecorder"`

By default, `redis://localhost:6379` will be used as the Redis DB host but a custom url can be set in the RedisURL sardana environemnt variable, e.g. `senv RedisURL "redis://localhost:6379"`

After performing a scan, the data will be stored in the RedisDB. For example, after the following scan:

```python
Door_macroserver_1 (READY) [218]: ascan dmot01 1 10 10 .1
Connected to redis://localhost:6379
Nexus writer saving is disabled, check NexusWriterOpts
This operation will not be stored persistently. Use "expconf" or "newfile" to configure data storage (or eventually "senv ScanFile <file name(s)>")
Error taking pre-scan snapshot of motLab03 (tango://localhost:10000/motor/lab_ipap_ctrl/3)
Scan #1 started at Tue Mar  5 17:58:13 2024. It will take at least 0:00:04.631810
 #Pt No    dmot01     ct01      ct02      ct03    ttdouble     dt   
   0         1        0.1       0.2       0.3     -235.649  0.901027
   1        1.9       0.1       0.2       0.3     -237.359  1.35695 
   2        2.8       0.1       0.2       0.3     -237.359  1.80936 
   3        3.7       0.1       0.2       0.3     -237.359  2.25279 
   4        4.6       0.1       0.2       0.3     -237.359  2.69835 
   5        5.5       0.1       0.2       0.3     -238.996  3.10914 
   6        6.4       0.1       0.2       0.3     -238.996   3.5545 
   7        7.3       0.1       0.2       0.3     -238.996  3.97729 
   8        8.2       0.1       0.2       0.3     -238.996   4.4224 
   9        9.1       0.1       0.2       0.3     -238.996  4.86705 
   10        10       0.1       0.2       0.3     -240.561  5.32753 
Scan #1 ended at Tue Mar  5 17:58:18 2024, taking 0:00:05.475096. Dead time 77.2% (setup time 3.3%, motion dead time 65.9%)
```

We can check that the data is in the redisDB with any viewer:

![](./docs/redis_screenshot.png)

But data can be easily accessed via blissdata, as it is explained in [blissdata documentation](https://bliss.gitlab-pages.esrf.fr/bliss/master/blissdata/getting_started.html). Existing scans can searched by its properties or be loaded by their keys. Blissdata can also wait for the next scans or load the last one collected. Then it is straightforward to get the data from the streams, for example:

```python
In [1]: from blissdata.redis_engine.store import DataStore

In [2]: from blissdata.redis_engine.exceptions import NoScanAvailable

In [3]: data_store = DataStore("redis://localhost:6379")

In [4]: try:
   ...:     timestamp, key = data_store.get_last_scan()
   ...: except NoScanAvailable:
   ...:     raise Exception("There is no scan at all !")
   ...: scan = data_store.load_scan(key)

In [5]: scan.name
Out[5]: 'a1scan'

In [6]: scan.number
Out[6]: 1

In [7]: scan.streams
Out[7]: 
{'#Pt No': <blissdata.redis_engine.stream.Stream at 0x7fc79c021730>,
 'dmot01': <blissdata.redis_engine.stream.Stream at 0x7fc79c021820>,
 'ct01': <blissdata.redis_engine.stream.Stream at 0x7fc73089b340>,
 'ct02': <blissdata.redis_engine.stream.Stream at 0x7fc73089bd00>,
 'ct03': <blissdata.redis_engine.stream.Stream at 0x7fc73089be80>,
 'ttdouble': <blissdata.redis_engine.stream.Stream at 0x7fc73089bfa0>,
 'dt': <blissdata.redis_engine.stream.Stream at 0x7fc73089bee0>}

In [8]: ttdouble = scan.streams['ttdouble']

In [9]: ttdouble[2]
Out[9]: -237.3587161542436
```

### Data Structure

You can find a very nice description of how the data is stored in [Bliss](https://bliss.gitlab-pages.esrf.fr/bliss/master/) documentation.


### Environment variables

There are three environment variables defined in the recorder:

```python
NX_EXP_INFO_ENV = "NexusExperimentInfo"
NX_WRITER_ENV = "NexusWriterOpts"
TANGO_WRITERS_ENV = "RedisWritersTango"
```
The `NexusExperimentInfo` is a dictionary containing information about the experiment, that will be stored in Redis (and used by the Nexus writer later if enabled) in the following format:

```
NexusExperimentInfo = 
{'beamline': 'bl99',
 'exp_desc': 'My nexus test experiment',
 'exp_id': 'test2024',
 'exp_team': [{'affiliation': 'LucasArts',
               'email': 'guy@scumm.org',
               'name': 'Guybrush Threepwood',
               'orcid': 'I do not have one',
               'role': 'pirate'},
              {'affiliation': 'LucasArts',
               'email': 'lech@scumm.org',
               'name': 'Lechuck',
               'orcid': '666',
               'role': 'bad pirate'}],
 'proposal_id': 11111111,
 'safety_info': 'red',
 'session': 'test_session'}
```

The `NexusWriterOpts` is a dictionary that sets up some parameters for the Nexus writer:

```
NexusWriterOpts = 
{'data_writer': 'nexus',
 'save': True,
 'scanFile': 'testNXwriter.h5',
 'singleNXFile': True}
```
- save: Enable/or disable the saving of the nexus file
- scanFile: Name of the nexus file to be saved (it will be inside `ScanDir`). An extension can be provided and a default can be set in the Recorder with the `DEFAULT_NX_EXT` variable. This is to avoid collision if a `ScanFile` with h5 extension is set that will use the default NXscan sardana recorder.
- data_writer: Name of the writer. Scans can use specific writers (and sessions) by its name.
- singleNXFile: Save in a single nexus file ({scandir}/{scanfile}.h5) all scans as different entries. If set to false, then three h5 files are created:
   - proposal_file: {scandir}/{proposal}_{beamline}.h5
   - collection_file: {scandir}/{scanfile}/{proposal}_{scanfile}.h5
   - dataset_file: {scandir}/{scanfile}/{scanfile}\_{scanNr}/{scanfile}_{scanNr}.h5


Macros are provided to populate these environment variables in the `sardana_redis_macros` library in the plugin macro folder of the plugin. To use them, add the path `$CONDA_PREFIX/lib/python3.9/site-packages/sardana_redis/macros/` in the MacroServer `MacroPath` property. The macros are:
- `nexus_writer_opts` to show current config and `nexus_writer_saving`, `nexus_writer_scanfile` and `nexus_writer_name` to write the values.
- `nexus_experiment_info` to show current info stored and `nexus_append_user`, `nexus_beamline`, `nexus_clear_users`,  `nexus_session_name`, `nexus_proposal_info`, `nexus_remove_user` and `nexus_safety_info` to set the info.

Finally `RedisWritersTango` environment var is a list of tango devices that may run writers so their state will be checked before the scan to see if they are active or not. 

```
RedisWritersTango = 
['blov/spec_writer/test', 'blov/bliss_nxwriter/test_session']
```
Bliss provides the Tango device for the Nexus writer as explained in the next section.


### Bliss Nexus Writer

As mentioned before, the Nexus writer service can be started from a script provided in Bliss.
```bash
$ ./startwriter.py --redis redis://localhost:6379 --session test_session --name nexus  # name is the writer name, should match the scan_info['data_writer'] to write the scan
INFO:blisswriter.subscribers.session_subscriber:[test_session (INIT)] Starting
INFO:blisswriter.subscribers.session_subscriber:[test_session (ON)] Subscribed to Redis
```
This starts a Nexus Writer called "nexus" that subscribes to the "test_session" and it will write the file when a scan is performed, if the `NexusWriterOpts` has been properly set.

```
INFO:blisswriter.subscribers.session_subscriber:[test_session (ON)] [a1scan (INIT)] Starting
INFO:blisswriter.subscribers.session_subscriber:[test_session (ON)] [a1scan (ON)] Subscribed to Redis
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] Start writing to '/tmp/test_240228/testNXwriter.h5' with options {'configurable': True, 'short_names': True, 'multivalue_positioners': False, 'flat': True, 'expand_variable_length': True, 'hold_file_open': True, 'locking': True, 'swmr': False, 'allow_external_nonhdf5': False, 'allow_external_hdf5': True, 'copy_non_external': False, 'required_disk_space': 200, 'recommended_disk_space': 1024, 'stack_mcas': False}
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Initialize subscan
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] Start writing subscan 'axis' to '/tmp/test_240228/testNXwriter.h5::/4.1'
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as STARTING in HDF5
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save 0 motor positions
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save scan user metadata
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save scan metadata
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as RUNNING in HDF5
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)]  9pts-10pts 512.0B 0:00:05.300743
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] Finalize scan
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Flush pending data
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Finalize subscan
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save 0 motor positions
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] No plots defined for saving
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save scan user metadata
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Save scan metadata
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as SUCCEEDED in HDF5
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (ON)] Finished writing to '/tmp/test_240228/testNXwriter.h5' (11pts-11pts 616.0B 0:00:05.841478)
INFO:blisswriter.subscribers.session_subscriber:[test_session (RUNNING)] [a1scan (OFF)] Finished succesfully
```

Bliss also offers a tango device called NexusWriterService. This device has still a small dependency on the Beacon server but the forked version at https://gitlab.com/alba-synchrotron/controls-section/bliss adds a `redisURL` property on the device that, when set, does not need the Beacon anymore. Also the property `session` needs to be set according to the session name configured by `NexusExperimentInfo` Sardana environment variable.

![](./docs/writer_tango_device.png)

Then, the TANGO device is launched, as usual, with the command

```bash
NexusWriterService <instance_name> --log=info
```

If the device name is set in `RedisWritersTango` environment variable, a scan will detect if the device is ON at the begining:

```
Door_macroserver_1 (READY) [264]: ascan dmot01 1 10 10 .1
blov/spec_writer/test is OFF
blov/bliss_nxwriter/test_session is ON
Connected to redis://localhost:6379
This operation will not be stored persistently. Use "expconf" or "newfile" to configure data storage (or eventually "senv ScanFile <file name(s)>")
Error taking pre-scan snapshot of motLab03 (tango://localhost:10000/motor/lab_ipap_ctrl/3)
Scan #5 started at Tue Mar  5 19:23:18 2024. It will take at least 0:00:04.631810
Scan URL /home/ovallcorba/dev_tests/sardana_dev/scans/test_240228/testNXwriter.h5::/5.1
 #Pt No    dmot01     ct01      ct02      ct03    ttdouble     dt   
   0         1        0.1       0.2       0.3     -35.6296  0.92306 
   1        1.9       0.1       0.2       0.3     -35.6296  1.40384 
   2        2.8       0.1       0.2       0.3     -35.6296   1.8554 
   3        3.7       0.1       0.2       0.3     -35.6296  2.28655 
...
```
And the same output as before can be seen in the NexusWriterService Device Server console when a file is written:
```
INFO  2024-03-05 19:14:28,928 blisswriter.subscribers.session_subscriber: [test_session (INIT)] Starting
INFO  2024-03-05 19:14:28,931 blisswriter.subscribers.session_subscriber: [test_session (ON)] Subscribed to Redis
Ready to accept request
INFO  2024-03-05 19:23:18,286 blisswriter.subscribers.session_subscriber: [test_session (ON)] [a1scan (INIT)] Starting
INFO  2024-03-05 19:23:18,286 blisswriter.subscribers.session_subscriber: [test_session (ON)] [a1scan (ON)] Subscribed to Redis
INFO  2024-03-05 19:23:18,338 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] Start writing to '/home/ovallcorba/dev_tests/sardana_dev/scans/test_240228/testNXwriter.h5' with options {'configurable': True, 'short_names': True, 'multivalue_positioners': False, 'flat': True, 'expand_variable_length': True, 'hold_file_open': True, 'locking': True, 'swmr': False, 'allow_external_nonhdf5': False, 'allow_external_hdf5': True, 'copy_non_external': False, 'required_disk_space': 200, 'recommended_disk_space': 1024, 'stack_mcas': False}
INFO  2024-03-05 19:23:18,361 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Initialize subscan
INFO  2024-03-05 19:23:18,366 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] Start writing subscan 'axis' to '/home/ovallcorba/dev_tests/sardana_dev/scans/test_240228/testNXwriter.h5::/5.1'
INFO  2024-03-05 19:23:18,367 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as STARTING in HDF5
INFO  2024-03-05 19:23:18,367 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save 0 motor positions
INFO  2024-03-05 19:23:18,367 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save scan user metadata
INFO  2024-03-05 19:23:18,433 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save scan metadata
INFO  2024-03-05 19:23:18,434 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as RUNNING in HDF5
INFO  2024-03-05 19:23:21,108 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] Finalize scan
INFO  2024-03-05 19:23:21,109 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Flush pending data
INFO  2024-03-05 19:23:21,109 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Finalize subscan
INFO  2024-03-05 19:23:21,110 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save 0 motor positions
INFO  2024-03-05 19:23:21,110 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] No plots defined for saving
INFO  2024-03-05 19:23:21,112 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save scan user metadata
INFO  2024-03-05 19:23:21,180 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Save scan metadata
INFO  2024-03-05 19:23:21,182 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] [axis] Scan marked as SUCCEEDED in HDF5
INFO  2024-03-05 19:23:21,186 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (ON)] Finished writing to '/home/ovallcorba/dev_tests/sardana_dev/scans/test_240228/testNXwriter.h5' (5pts-5pts 280.0B 0:00:02.900337)
INFO  2024-03-05 19:23:21,186 blisswriter.subscribers.session_subscriber: [test_session (RUNNING)] [a1scan (OFF)] Finished succesfully

```

![](./docs/nexus_file_silx.png)


### Basic Spec Writer Example

A very simple spec writer as a writer client example is provided as a [standalone process](./sardana_redis/spec_writer/spec_writer_service.py) or as a [tango device](./sardana_redis/spec_writer/spec_writer_tango.py).

After registering it to a tangoDB with <instance_name> the following properties can be defined:

Three properties can be defined:
- redis_url: Redis DB url (default='redis://localhost:6379')
- log_level: Log level of spec_writer_service (default='INFO')
next_scan_timeout: Timeout for get_next_scan calls. Use 0 for blocking calls. The only drawback is that blocking prevents stopping the service from the tango device at a specific moment (it will be applied after the following scan) (default=2)

And it can be started normally as (e.g. specwriter instance name):

```bash
python spec_writer_tango.py specwriter -v4
2023-12-21T17:10:51,766524+0100 INFO (spec_writer_tango.py:18) blov/spec_writer/test Initializing device...
2023-12-21 17:10:51,766 - sardana_redis.spec_writer.spec_writer_service - INFO - Connecting to DB
2023-12-21 17:10:51,771 - sardana_redis.spec_writer.spec_writer_service - INFO - Waiting for scan
Ready to accept request
Processing scan esrf:scan:01HJ6JG89DE0Z2Z2A2KMDPRM3H
2023-12-21 17:14:26,842 - sardana_redis.spec_writer.spec_writer_service - INFO - recording into '/tmp/scans/test_spec_writer.dat'
2023-12-21 17:14:43,680 - sardana_redis.spec_writer.spec_writer_service - WARNING - End of stream for scalar column #Pt No
2023-12-21 17:14:43,690 - sardana_redis.spec_writer.spec_writer_service - INFO - finished recording to '/tmp/scans/test_spec_writer.dat'
2023-12-21 17:14:43,690 - sardana_redis.spec_writer.spec_writer_service - INFO - Waiting for next scan
```

And data will be written/appended to the file in spec format:

```
#S 74 ascanct mot04 1.0 10.0 10 0.1 0.2
#D 2023-12-21T17:14:26.605568+01:00
#C Acquisition started at 2023-12-21T17:14:26.605568+01:00
#O0 dcm_kev  dmot01  mot01  mot02  mot03  mot04  motLab01  motLab02
#O1 motLab03  pd_mc  pd_oc
#P0 0.0 0.0 0.0 0.0 0.0 10.0 -137136.0 1000.0
#P1 2000.0 0.0 0.0
#N 7
#@MCA 1024
#@CHANN 1024 0 1023 1
#@MCA_NB 1
#@DET_0 oned01
#L #Pt_No  mot04  ct01  ct02  ct03  ct04  dt
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
0 1.0 0.1 0.2 0.30000000000000004 0.4 2.0                              
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
1 1.9 0.1 0.2 0.30000000000000004 0.4 2.3                              
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
2 2.8 0.1 0.2 0.30000000000000004 0.4 2.5999999999999996               
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
3 3.7 0.1 0.2 0.30000000000000004 0.4 2.8999999999999995               
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
4 4.6 0.1 0.2 0.30000000000000004 0.4 3.1999999999999993               
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
5 5.5 0.1 0.2 0.30000000000000004 0.4 3.499999999999999                
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
6 6.4 0.1 0.2 0.30000000000000004 0.4 3.799999999999999                
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
7 7.3 0.1 0.2 0.30000000000000004 0.4 4.099999999999999                
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
8 8.2 0.1 0.2 0.30000000000000004 0.4 4.399999999999999                
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
9 9.1 0.1 0.2 0.30000000000000004 0.4 4.699999999999998                
@A 2.9802322387695314e-09 3.188948758273692e-09 3.4118304746830744e-09 ...
10 10.0 0.1 0.2 0.30000000000000004 0.4 4.999999999999998
#C Acquisition ended 2023-12-21T17:14:43.687924+01:00
```




