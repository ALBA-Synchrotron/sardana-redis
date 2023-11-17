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

### Installation
To use the [Sardana Redis BlissData 1.0 Recorder](./sardana_redis-10/recorder/redis_bliss_recorder.py),  a Redis database and the module [Blissdata 1.0](https://gitlab.esrf.fr/bliss/bliss/-/tree/blissdata-1.0.0rc0/blissdata) are required.

A local redisDB can be started from the provided docker compose file. The blredis.conf configuration will be used and the DB will be exposed in `localhost:6379`.

Install the plugin from the setup.py file and edit the Sardana Macroserver RecorderPath property to point to the folder where the RedisBlissRecorder is.

Then the recorder can be activated by setting it in spock with the command `senv DataRecorder "RedisBlissRecorder"`

By default, `localhost:6379` will be used as the redisDB but a custom url can be set in the RedisURL sardana environemnt variable, e.g. `senv RedisURL "redis://localhost:6379"`


### Usage




### Bliss Nexus writer service