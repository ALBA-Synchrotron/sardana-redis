from sardana.macroserver.scan.recorder import DataRecorder
from sardana.macroserver.msexception import UnknownEnv

from sardana_redis.utils.sardana_redis_utils import set_redis_db
from blissdata.redis_engine.scan import Scan, ScanState
from blissdata.redis_engine.encoding.numeric import NumericStreamEncoder
from blissdata.redis_engine.encoding.json import JsonStreamEncoder
import os
import datetime


class RedisBlissRecorder(DataRecorder):
    """
    Redis database Blissdata 1.0 recorder

    Put the directory where this file resides in RecorderPath MacroServer tango property
    and then senv ScanRecorder "['RedisBlissRecorder']
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        macro = kwargs['macro']

        try:
            redisURL = macro.getMacroServer().get_env("RedisURL")
        except UnknownEnv:
            macro.getMacroServer().set_env("RedisURL", "redis://localhost:6379")
            redisURL = "redis://localhost:6379"

        set_redis_db(redisURL)

        scanDir = macro.getMacroServer().get_env("ScanDir")
        scanFile = macro.getMacroServer().get_env("ScanFile")[0]
        scanPath = os.path.join(scanDir, scanFile)
        scanID = macro.getMacroServer().get_env("ScanID")

        # TODO check ScanFile extensions to set the writer? (nexus, spec...)
        # TODO take some info about proposalnr, user, dataset, etc.. from env?

        # The identity model we use is ESRFIdentityModel in blissdata.redis_engine.models
        # It defines the json fields indexed by RediSearch
        scan_id = {
            "name": macro.name,
            "number": scanID,
            "data_policy": "no_policy",
            "session": "test_session",
            "path": scanPath,
            # 'proposal': 'id002311',
            # 'collection': 'sample',
            # 'dataset': '0001',
        }

        scan_info = {
            "name": macro.name,
            'save': True,
            'data_writer': 'nexus',
            "filename": scanPath,
            "acquisition_chain": {},
            'npoints': macro.nb_points,
            'count_time': macro.integ_time,
            'scan_nb': scanID,
            'sleep_time': macro.latency_time,
            'stab_time': None,
            'start': [-1],
            'start_time': datetime.datetime.now().astimezone().isoformat(),
            'stop': [1],
            'technique': {'@NX_class': 'NXcollection'},
            'title': macro.macro_command,
            'type': macro._name,
            'user_name': 'ovallcorba',
            'writer_options': {'chunk_options': {}, 'separate_scan_files': None},
            'nexuswriter': {}
        }

        # create scan in the database
        self.scan = Scan.create(scan_id, info=scan_info)

    def _startRecordList(self, recordlist):

        header = dict(recordlist.getEnviron())

        # sanitize numpy.int64 types
        datadesc = []
        for col in header['datadesc']:
            col = col.toDict()
            shape = col.get('shape')
            if shape:
                col['shape'] = [int(dim) for dim in shape]
            datadesc.append(col)
        # self.scan.info["datadesc"] = datadesc
        datadesc_list = list(datadesc)

        snapshot = []
        for col in header.get('preScanSnapShot', ()):
            data = col.toDict()
            try:
                data['value'] = col.pre_scan_value
            except AttributeError:
                data['value'] = None
            snapshot.append(data)
        # self.scan.info['preScanSnapShot'] = snapshot

        # we want to avoid import bliss (from bliss.scanning import chain)
        # build manually the necessary dicts.
        device_dict = {}
        device_dict["timer"] = {'channels': []}
        device_dict["counters"] = {'channels': [], 'metadata': {}}
        device_dict["axis"] = {'channels': [], 'metadata': {}}
        acq_chain_dict = {}
        channels_dict = {}

        # Add as metadata the full datadesc and snapshot
        snap_dict = {}
        ddesc_dict = {}
        for elem in datadesc_list:
            ddesc_dict[elem["label"]] = elem
        for elem in snapshot:
            snap_dict[elem["label"]] = elem

        self.scan.info["snapshot"] = snap_dict
        self.scan.info["datadesc"] = ddesc_dict
        self.scan.info['scan_meta_categories'] = ['positioners',
                                                  'nexuswriter',
                                                  'instrument',
                                                  'technique',
                                                  'snapshot',
                                                  'datadesc']

        # declare the streams in the scan (all Numeric in our test, TODO: consider references, 1d,...)
        self.stream_list = {}
        for elem in datadesc_list:
            if "point_nb" in elem["name"]:
                continue

            name = elem["name"]
            label = elem["label"]
            dtype = elem["dtype"]
            shape = elem["shape"]
            unit = ""
            if "unit" in elem:
                unit = elem["unit"]

            device_type = "axis"
            if "timestamp" in label:
                device_type = "timer"
            elif name in header["counters"]:
                device_type = "counters"
            device_dict[device_type]['channels'].append(label)
            channels_dict[label] = {"device": device_type,
                                    "dim": len(shape),
                                    "display_name": label}

            # Check dtype and shape for the type of stream to use
            encoder = NumericStreamEncoder(dtype=dtype, shape=shape)
            scalar_stream = self.scan.create_stream(
                label, encoder, info={"unit": unit})

            # keep the list of streams for writerecord
            self.stream_list[name] = scalar_stream

        # this does the trick to have a valid acquisition chain
        acq_chain_dict["axis"] = {'devices': list(device_dict.keys()),
                                  'master': {'images': [],
                                             'scalars': device_dict["axis"]["channels"]},
                                  'scalars': device_dict["timer"]["channels"] + device_dict["counters"]["channels"]}

        self.scan.info["devices"] = device_dict
        self.scan.info["channels"] = channels_dict
        self.scan.info["acquisition_chain"] = acq_chain_dict

        self.scan.prepare()  # upload initial metadata and stream declarations

        # Scan is ready to start, eventually wait for other processes.
        # Sharing stream keys to external publishers can be done there.

        self.scan.start()

    def _endRecordList(self, recordlist):
        for stream in self.stream_list.values():
            try:
                stream.seal()
            except Exception as e:
                print(e)
                self.warning(
                    "Error sealing stream {} not found".format(stream.name))
                continue

        self.scan.stop()

        # gather end of scan metadata if necessary
        # self.scan.info["end_metadata"] = {"c": 123, "d": "xyz"}

        self.scan.close()  # upload final metadata

    def _writeRecord(self, record):
        ctdict = record.data.items()
        for k, v in ctdict:
            try:
                ch_stream = self.stream_list[k]
            except KeyError:
                self.warning("Stream for {} not found".format(k))
                continue
            ch_stream.send(v)
