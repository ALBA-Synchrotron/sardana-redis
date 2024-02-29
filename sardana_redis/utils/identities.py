from typing import Optional
from redis_om import HashModel, Field
from blissdata.redis_engine.identities import _UninitializedRedis

class ALBAIdentityModel(HashModel):
    """Institute specific information used to link scans in Redis to external services."""

    class Meta:
        global_key_prefix = "esrf"  # FIXME cannot use alba here yet since memorytracker and writer does not expose the identity option when creating datastore object
        model_key_prefix = "id"
        database = _UninitializedRedis()

    name: str = Field(index=True)
    number: int = Field(index=True)
    data_policy: str = Field(index=True)
    
    # data policy
    beamline: Optional[str] = Field(index=True)
    session: Optional[str] = Field(index=True)
    proposal: Optional[str] = Field(index=True)
    collection: Optional[str] = Field(index=True)
    dataset: Optional[str] = Field(index=True)

    # Without data policy
    path: Optional[str] = Field(index=True)