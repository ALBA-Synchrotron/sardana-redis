from blissdata.redis_engine import set_redis_url, init_redis_db


def set_redis_db(redisURL):
    
    try:
        init_redis_db("redis://localhost:6379")  # this has to be done once only after starting DB
    except Exception as e:
        print(e)
        print("error initializing redis, already initialized??")
        
    try:
        set_redis_url("redis://localhost:6379")  # this only once per client
    except Exception as e:
        print(e)
        print("error setting redis url, already set??")

    # we also need to run:  memory_tracker --redis-url redis://localhost:6379