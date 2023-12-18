from sardana.macroserver.scan.recorder import DataRecorder
from sardana.macroserver.msexception import UnknownEnv

from sardana_redis.utils.sardana_redis_utils import get_data_store
from blissdata.redis_engine.encoding.numeric import NumericStreamEncoder
from blissdata.schemas.scan_info import ScanInfoDict, DeviceDict, ChainDict, ChannelDict
import os
import datetime
import sardana


class RedisBlissRecorder(DataRecorder):
    """
    Redis database Blissdata 1.0 recorder

    Put the directory where this file resides in RecorderPath MacroServer tango property
    and then senv ScanRecorder "['RedisBlissRecorder']"
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        macro = kwargs['macro']

        try:
            redisURL = macro.getMacroServer().get_env("RedisURL")
        except UnknownEnv:
            macro.getMacroServer().set_env("RedisURL", "redis://localhost:6379")
            redisURL = "redis://localhost:6379"

        data_store = get_data_store(redisURL)

        scanDir = macro.getMacroServer().get_env("ScanDir")
        scanFile_env = macro.getMacroServer().get_env('ScanFile')
        allowed_extensions = ['.h5', '.hdf5']
        if isinstance(scanFile_env, str):
            scanFile = scanFile_env
        else:
            # search the element that has the .h5 or .hdf5 extension
            scanFile = next(
                (f for f in scanFile_env if f.endswith(tuple(allowed_extensions))),
                None,
            )
        # TODO check for more ScanFile extensions to set the writer? (nexus, spec...)
        if scanFile is None:
            raise ValueError(
                "No valid ScanFile found in ScanFile Sardana environment variable"
            )

        scanPath = os.path.join(scanDir, scanFile)
        scanID = macro.getMacroServer().get_env("ScanID")

        # TODO take some info about proposalnr, user, dataset, etc.. from env?
        try:
            info_env = macro.getMacroServer().get_env("NexusExperimentInfo")
            proposal = info_env['proposal_id']
        except (UnknownEnv, KeyError):
            self.warning(
                "NexusExperimentInfo Sardana environment variable not found")
            proposal = "None"

        scan_id = {
            "name": macro.name,
            "number": scanID,
            "data_policy": "no_policy",
            "session": "test_session",
            "path": scanPath,
            'proposal': proposal,
            # 'collection': 'sample',
            # 'dataset': '0001',
        }

        scan_info = ScanInfoDict(
            acquisition_chain={},
            channels={},
            devices={},
            sequence_info={},
            group='',
            start_time=datetime.datetime.now().astimezone().isoformat(),
            scan_nb=scanID,
            index_in_sequence=1,
            retry_nb=0,
            is_scan_sequence=False,
            type=macro._name,
            title=macro.macro_command,
            npoints=macro.nb_points,
            count_time=macro.integ_time,
            sleep_time=macro.latency_time,
            stab_time=None,
            data_policy='no_policy',
            data_writer='nexus',
            writer_options={'chunk_options': {}, 'separate_scan_files': None},
            publisher='Sardana',
            publisher_version=sardana.__version__,
            save=True,
            session_name='demo_session',
            user_name='tangosys',
            plots=[],
            _display_extra={},
            name=macro.macro_command,
            filename=scanPath,
        )

        # create scan in the database
        self.scan = data_store.create_scan(scan_id, info=scan_info)

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
        datadesc_list = list(datadesc)

        snapshot = []
        for col in header.get('preScanSnapShot', ()):
            data = col.toDict()
            try:
                data['value'] = col.pre_scan_value
            except AttributeError:
                data['value'] = None
            snapshot.append(data)

        # build the necessary dicts
        devices: dict[str, DeviceDict] = {}
        devices["timer"] = DeviceDict(channels=[], metadata={})
        devices["counters"] = DeviceDict(channels=[], metadata={})
        devices["axis"] = DeviceDict(channels=[], metadata={})

        acq_chain: dict[str, ChainDict] = {}
        channels: dict[str, ChannelDict] = {}

        # Add as metadata the full datadesc and snapshot
        snap_dict = {}
        ddesc_dict = {}
        for elem in datadesc_list:
            ddesc_dict[elem["label"]] = elem
        for elem in snapshot:
            snap_dict[elem["label"]] = elem

        self.scan.info["snapshot"] = snap_dict
        self.scan.info["datadesc"] = ddesc_dict
        self.scan.info['scan_meta_categories'] = ['snapshot', 'datadesc']

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
            devices[device_type]['channels'].append(label)
            channels[label] = ChannelDict(device=device_type,
                                          dim=len(shape),
                                          display_name=label)

            # Check dtype and shape for the type of stream to use
            encoder = NumericStreamEncoder(dtype=dtype, shape=shape)
            scalar_stream = self.scan.create_stream(
                label, encoder, info={"unit": unit})

            # keep the list of streams for writerecord
            self.stream_list[name] = scalar_stream

        # this does the trick to have a valid acquisition chain
        acq_chain["axis"] = ChainDict(devices=list(devices.keys()))
        self.scan.info["devices"] = devices
        self.scan.info["channels"] = channels
        self.scan.info["acquisition_chain"] = acq_chain

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
                    "Error sealing stream {}".format(stream.name))
                continue

        self.scan.stop()

        self.scan.info['end_time'] = datetime.datetime.now().astimezone().isoformat()
        self.scan.info['end_reason'] = 'SUCCESS'
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
