# Sardana Redis tests

To set up a development environment, the first step is to have a Sardana system and a Redis DB.

For the RedisDB we can set up a docker container exposing the 6379 port in localhost:

```bash
version: '3'

services:
  redis7:
    image: redis/redis-stack-server:7.2.0-v5
    hostname: redis7
    container_name: redis7
    environment:
        - REDIS_ARGS=/usr/local/etc/redis/redis.conf
    ports:
      - 6379:6379
    volumes:
      - ./blredis.conf:/usr/local/etc/redis/redis.conf
    command: redis-server /usr/local/etc/redis/redis.conf --loglevel warning --protected-mode no --loadmodule /opt/redis-stack/lib/redisearch.so --loadmodule /opt/redis-stack/lib/rejson.so 
    restart: on-failure
```
Then we would be able to connect to this database using the host localhost:6379

## Sardana Redis BlissData 1.0 Recorder

### Data structure
(TODO)
### Usage
To use the [Sardana Redis BlissData 1.0 Recorder](./sardana_redis-10/recorder/redis_bliss_recorder.py), the module [Blissdata 1.0](https://gitlab.esrf.fr/bliss/bliss/-/tree/blissdata-1.0.0rc0/blissdata) is required. 

Modify if necessary the url:port of the RedisDB and then edit the Sardana Macroserver RecorderPath property to point to the folder where the RedisBlissRecorder is.

Then we can activate the Recorder by setting it in spock with 
```python
Door_ms_red_1 [2]: senv DataRecorder "RedisBlissRecorder"
Door_ms_red_1 [1]: lsenv
                  Name                                                          Value    Type
 --------------------- -------------------------------------------------------------- -------
             _SAR_DEMO   {'controllers': ['motctrl03', 'ctctrl03', 'zerodctrl03 [...]    dict
          _ViewOptions   {'ShowCtrlAxis': False, 'OutputBlock': False, 'PosForm [...]    dict
          ActiveMntGrp                                                     test_redis     str
   DataCompressionRank                                                              1     int
          DataRecorder                                             RedisBlissRecorder     str
       PreScanSnapshot                                                             []    list
               ScanDir                                         /workspace/tests_scans     str
              ScanFile                                             ['testRedisRec01']    list
           ScanHistory   [{'startts': 1689178084.7259643, 'endts': 1689178089.9 [...]    list
                ScanID                                                            131     int
```
