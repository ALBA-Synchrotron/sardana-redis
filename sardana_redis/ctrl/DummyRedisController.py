import datetime
from sardana import State
from sardana.pool.poolcontrollers.DummyCounterTimerController import DummyCounterTimerController
from sardana.pool.controller import Type, Description, DefaultValue
from sardana_redis.utils.sardana_redis_utils import get_data_store
from blissdata.redis_engine.encoding.numeric import NumericStreamEncoder


class DummyRedisController(DummyCounterTimerController):
    """This class is the Tango Sardana Redis CounterTimer controller for testing"""

    ctrl_properties = \
        {
            'RedisURL': {Type: str,
                         Description: "Redis DB server url and port",
                         DefaultValue:  "redis://localhost:6379"},
        }

    ctrl_extra_attributes = \
        {
            "LastScanKEY": {
                Type: str,
                Description: "Last Scan Redis Key",
            },
        }
    DummyCounterTimerController.ctrl_attributes.update(ctrl_extra_attributes)
    
    def __init__(self, inst, props, *args, **kwargs):
        DummyCounterTimerController.__init__(
            self, inst, props, *args, **kwargs)
        self.data_store = get_data_store(self.RedisURL)
        if self.data_store is None:
            raise Exception(
                "No Redis connection. Set RedisURL environment variable. Data will not be published")
        self.stream_list = {}

        self.scan = None
        self._state = State.On
        self._status = 'On'
        self._scanNr = 0
        self._pointNr = 0
        self._key = None
        self._enablePublication = False
        self._scanStarted = False
        self._totalPoints = 0
        self._pointsPerChan = {}

    def getLastScanKEY(self):
        return self._key

    def StateOne(self, axis):
        self._log.debug('StateOne(%d): entering...' % axis)
        self._state, self._status = DummyCounterTimerController.StateOne(
            self, axis)
        return self._state, self._status

    def StateAll(self):
        self._log.debug('StateAll: entering...')
        if self._scanStarted and self._enablePublication:
            for stream in self.stream_list.values():
                if not stream.is_sealed():
                    return
            # All streams sealed. Close scan.
            self._log.debug('Closing scan {}'.format(self.scan.key))
            self.scan.stop()
            self.scan.info['end_time'] = datetime.datetime.now(
            ).astimezone().isoformat()
            self.scan.info['end_reason'] = 'SUCCESS'
            self.scan.close()
            self._scanStarted = False
            self._enablePublication = False

    def PrepareOne(self, axis, expo_time, repetitions, latency_time, nb_starts):
        self._log.debug('PrepareOne: entering...')
        if repetitions == 1 and nb_starts == 1:
            self._enablePublication = False
            return
        # scan
        self._enablePublication = True
        self._totalPoints = repetitions * nb_starts

        self.name = "DummyRedisController"
        scan_id = {
            "name": self.name,
            "number": self._scanNr,
            "data_policy": "no_policy",
            "session": "session",
            "path": "scanPath",
            "proposal": "proposal",
            "beamline": "beamline",
        }

        # Create scan in the database
        self.scan = self.data_store.create_scan(
            scan_id, info={"name": self.name})
        self._key = self.scan.key
        self._log.info("Scan KEY {}".format(self.scan.key))
        self._pointNr = 0
        self._scanStarted = False
        self._scanExpChan = []

    def PreStartOne(self, axis, value=None):
        self._log.debug('PreStartOne(%d): entering...' % axis)
        DummyCounterTimerController.PreStartOne(self, axis, value)
        if not self._enablePublication:
            return True
        if not self._scanStarted:
            self._scanExpChan.append(axis)
            self._pointsPerChan[axis] = 0
        return True

    def StartAll(self):
        self._log.debug('StartAll: entering...')
        DummyCounterTimerController.StartAll(self)
        if not self._enablePublication:
            return
        if not self._scanStarted:
            self._scanStarted = True
            # Create streams here taking the list of axis from PreStartOne
            for axis in self._scanExpChan:
                encoder = NumericStreamEncoder(dtype=float, shape=())
                scalar_stream = self.scan.create_stream(
                    "axis{}".format(axis), encoder, info={})
                self.stream_list[axis] = scalar_stream
            self.scan.prepare()
            # Scan is ready to start, eventually wait for other processes.
            # Sharing stream keys to external publishers can be done there.
            self.scan.start()

    def ReadOne(self, axis):
        self._log.debug('ReadOne(%d): entering...' % axis)
        value = DummyCounterTimerController.ReadOne(self, axis)

        if not self._enablePublication:
            return value

        if self._state == State.Moving:
            return value

        # Finished counting, publishing to Redis
        try:
            ch_stream = self.stream_list[axis]
            ch_stream.send(value)  # TODO check if value is SardanaValue since stream.send() allows lists or scalars.
        except KeyError:
            self._log.error("Stream for {} not found".format(axis))
        except Exception as e:
            self._log.error(e)

        if isinstance(value, list):
            self._pointsPerChan[axis] += len(value)
        else:
            self._pointsPerChan[axis] += 1

        if self._pointsPerChan[axis] >= self._totalPoints:
            ch_stream.seal()
            self.StateAll()  # FIXME find another way

        return value
