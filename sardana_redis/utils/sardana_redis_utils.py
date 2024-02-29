# from blissdata.redis_engine import set_redis_url, init_redis_db
from blissdata.redis_engine.store import DataStore
from sardana_redis.utils.identities import ALBAIdentityModel

# We could use another identity model (e.g. ALBAIdentityModel) but 
# then it needs to be specified as well when creating the DataStore 
# object in the NexusWriter and the memory_tracker

def get_data_store(redisURL):
    
    data_store = None
    try:
        data_store = DataStore(redisURL, init_db=True, identity_model_cls=ALBAIdentityModel)
    except Exception as e:
        print(e)
        print("error initializing redis , already initialized??")

    try:
        data_store = DataStore(redisURL, identity_model_cls=ALBAIdentityModel)
    except Exception as e:
        print(e)
        print("error setting redis url, already set??")

    return data_store
