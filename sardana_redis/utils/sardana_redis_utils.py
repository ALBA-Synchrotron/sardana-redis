# from blissdata.redis_engine import set_redis_url, init_redis_db
from blissdata.redis_engine.store import DataStore
from sardana_redis.utils.identities import ALBAIdentityModel

def get_data_store(redisURL):

    try:
        data_store = DataStore("redis://localhost:6379", init_db=True)  #, identity_model_cls=ALBAIdentityModel)
    except Exception as e:
        print(e)
        print("error initializing redis , already initialized??")

    try:
        data_store = DataStore("redis://localhost:6379")  #, identity_model_cls=ALBAIdentityModel)
    except Exception as e:
        print(e)
        print("error setting redis url, already set??")

    return data_store
    # we also need to run:  memory_tracker --redis-url redis://localhost:6379