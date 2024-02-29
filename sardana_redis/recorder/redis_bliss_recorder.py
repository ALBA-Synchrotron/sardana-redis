from sardana.macroserver.scan.recorder import DataRecorder
from sardana.macroserver.msexception import UnknownEnv

from sardana_redis.utils.sardana_redis_utils import get_data_store
from blissdata.redis_engine.encoding.numeric import NumericStreamEncoder
from blissdata.schemas.scan_info import ScanInfoDict, DeviceDict, ChainDict, ChannelDict
import os
import tango
import datetime
import h5py
import typing


NX_EXP_INFO_ENV = "NexusExperimentInfo"
TANGO_WRITERS_ENV = "RedisWritersTango"
NX_WRITER_EXT = ['.h5', '.hdf5', '.nexus']


def scan_exists(dataset_file: str, scan_number: int) -> bool:
    if not os.path.exists(dataset_file):
        return False
    with h5py.File(dataset_file, "r", locking=False) as nxroot:
        return f"{scan_number}.1" in nxroot


def validate_scan_info(scan_info: dict) -> ScanInfoDict:
    """Copy paste of validator code from bliss.scanning.scan_info"""
    try:
        from pydantic import BaseModel, ConfigDict
    except ImportError:
        print("pydantic not available. Scan info validation skipped")
        return scan_info

    return scan_info

    # FIXME The validation does not work for me at the moment,
    # it does not take into account the NotRequired attributes
    class Holder(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        scan_info: ScanInfoDict

    valid_scan_info = typing.cast(ScanInfoDict, scan_info)
    Holder(scan_info=valid_scan_info)  # This trig the validation
    return valid_scan_info


class RedisBlissRecorder(DataRecorder):
    """
    Redis database Blissdata 1.0 recorder

    Put the directory where this file resides in RecorderPath MacroServer tango property
    and then senv ScanRecorder or DataRecorder as "['RedisBlissRecorder']"
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.macro = kwargs['macro']

        try:
            redisURL = self.macro.getMacroServer().get_env("RedisURL")
        except UnknownEnv:
            self.macro.getMacroServer().set_env("RedisURL", "redis://localhost:6379")
            redisURL = "redis://localhost:6379"

        self.checkWriters()
        data_store = self.getRedisDataStore(redisURL)
        if data_store is None:
            self.error(
                "No Redis connection. Set RedisURL environment variable. Data will not be published")
            return

        self.nexus_save = True
        self.nx_save_single_file = True  # TODO expose option somewhere
        scanPath = self.getScanPath()
        # If no ScanDir or ScanFile are set (or properly set), the save flag on scan_info
        # will be set to false
        if scanPath is None:
            self.nexus_save = False

        scanID = self.macro.getMacroServer().get_env("ScanID")

        # Get some info about proposalnr, user, dataset, etc.. from env
        try:
            info_env = self.macro.getMacroServer().get_env(NX_EXP_INFO_ENV)
            proposal = info_env['proposal_id']
            beamline = info_env['beamline']
        except (UnknownEnv, KeyError):
            self.warning(
                "{} Sardana environment variable not found".format(NX_EXP_INFO_ENV))
            proposal = "None"

        scan_id = {
            "name": self.macro.name,
            "number": scanID,
            "data_policy": "no_policy",
            "session": "test_session",
            "path": scanPath,
            "proposal": proposal,
            "beamline": beamline,
            # 'collection': 'sample',
            # 'dataset': '0001',
        }

        # create scan in the database
        # nx writer needs the name when createing scan
        self.scan = data_store.create_scan(
            scan_id, info={"name": self.macro.name})

    def checkWriters(self):
        """Check the status of Redis writers defined in Sardana env variable"""
        try:
            redisWriters = self.macro.getMacroServer().get_env(TANGO_WRITERS_ENV)
            for writer in redisWriters:
                writer_dev = tango.DeviceProxy(writer)
                try:
                    if writer_dev.State() == tango.DevState.ON:
                        self.macro.info("%s is ON" % writer)
                    else:
                        self.macro.warning("%s is OFF" % writer)
                except:
                    self.macro.warning("%s is OFF" % writer)
        except UnknownEnv:
            self.macro.warning(
                "No {} environment variable found".format(TANGO_WRITERS_ENV))

    def getRedisDataStore(self, redisURL):
        data_store = None
        try:
            data_store = get_data_store(redisURL)
            if data_store is None:
                self.macro.error(
                    "ERROR: Could not connect to RedisDB: %s" % redisURL)
            else:
                self.macro.info("Connected to {}".format(data_store))
        except Exception as e:
            self.macro.error(
                "ERROR: Could not connect to RedisDB: %s" % redisURL)
        return data_store

    def getScanPath(self):
        try:
            self.scanDir = self.macro.getMacroServer().get_env("ScanDir")
            scanFile_env = self.macro.getMacroServer().get_env('ScanFile')
            nexus_writer_opts = self.macro.getMacroServer().get_env(NX_WRITER_ENV)

            scanPath = None

            if self.scanDir is None or scanFile_env is None:
                return scanPath

            if isinstance(scanFile_env, str):
                self.scanFile = scanFile_env
            else:
                # search the element that has the NX writer ext as it may be that
                # other scanwriters are also used (e.g. spec)
                self.scanFile = next(
                    (f for f in scanFile_env if f.endswith(tuple(NX_WRITER_EXT))),
                    None,
                )

            if self.scanFile is None:
                msg = ("No valid ScanFile found in ScanFile Sardana environment variable\n" +
                       "Allowed extensions for NX writer are: {}\n".format(NX_WRITER_EXT) +
                       "Data will not be written by Nexus writer service")
                self.error(msg)
                scanPath = None
            else:
                scanPath = os.path.join(self.scanDir, self.scanFile)

        except UnknownEnv:
            msg = ("No ScanDir/ScanFile environment variable found\n" +
                   "Data will not be written by Nexus writer service")
            self.macro.error(msg)
            self.scanDir = None
            self.scanFile = None
            scanPath = None

        return scanPath

    def file_info(self, singleFile=True):
        """
        if singleFile==True, only the h5 dataset_file is created as
          - {scandir}/{scanfile}.h5
        and imagesPath is set at {scandir}/scan{scanNr}
        All scans go to different entries inside the same dataset_file

        if singleFile==False, then three h5 files created:
          - proposal file: {scandir}/{proposal}_{beamline}.h5
          - collection_file: {scandir}/{scanfile}/{proposal}_{scanfile}.h5
          - dataset_file: {scandir}/{scanfile}/{scanfile}_{scanNr}/{scanfile}_{scanNr}.h5
        and imagesPath is set at {scandir}/{scanfile}/{scanfile}_{scanNr}/scan{scanNr}
        All scanss in different h5 files (and referenced by collection and proposal files)
        """
        if not self.nexus_save:
            return None, {}, None

        collection = os.path.splitext(self.scanFile)[0]
        exp_folder = self.scanDir
        beamline = self.scan.beamline
        proposal = self.scan.proposal
        dataset_nr = self.scan.number

        if singleFile:
            dataset_file = os.path.join(
                self.scanDir, "{}.h5".format(collection))
            images_path = os.path.join(
                self.scanDir, "scan{:04d}".format(self.scan.number))
            masterfiles = {}
        else:
            proposal_file = os.path.join(
                exp_folder, f"{proposal}_{beamline}.h5")
            collection_file = os.path.join(
                exp_folder, collection, f"{proposal}_{collection}.h5")
            dataset_file = os.path.join(
                exp_folder, collection, f"{collection}_{dataset_nr}", f"{collection}_{dataset_nr}.h5"
            )
            while scan_exists(dataset_file, self.scan.number):
                dataset_nr = f"{int(dataset_nr)+1:04d}"
                dataset_file = os.path.join(
                    exp_folder,
                    collection,
                    f"{collection}_{dataset_nr}",
                    f"{collection}_{dataset_nr}.h5",
                )
            images_path = os.path.join(
                exp_folder, collection, f"{collection}_{dataset_nr}", f"scan{self.scan.number:04d}"
            )
            masterfiles = {
                "dataset": dataset_file,
                "dataset_collection": collection_file,
                "proposal": proposal_file,
            }

        self.macro.info("Scan URL %s::/%d.1", dataset_file, self.scan.number)
        return dataset_file, masterfiles, images_path

    def scan_info(self, snap_dict, ddesc_dict):
        # Files like at the ESRF (not required to do it like this)
        filename, masterfiles, images_path = self.file_info(
            singleFile=self.nx_save_single_file)

        scan_info = {
            ##################################
            # Scan metadata
            ##################################
            "name": self.scan.name,
            "scan_nb": self.scan.number,
            "session_name": self.scan.session,
            "data_policy": self.scan.data_policy,
            "start_time": datetime.datetime.now().astimezone().isoformat(),
            "title": self.macro.macro_command,
            "type": self.macro._name,
            "npoints": self.macro.nb_points,
            "count_time": self.macro.integ_time,
            ##################################
            # Device information
            ##################################
            "acquisition_chain": self.acq_chain,
            "devices": self.devices,
            "channels": self.channels,
            ##################################
            # Plot metadata
            ##################################
            "display_extra": {"plotselect": []},
            "plots": [],
            ##################################
            # NeXus writer metadata
            ##################################
            "save": self.nexus_save,
            "filename": filename,
            "images_path": images_path,
            "publisher": "test",
            "publisher_version": "1.0",
            "data_writer": "nexus",
            "writer_options": {"chunk_options": {}, "separate_scan_files": False},
            "scan_meta_categories": [
                "positioners",
                "nexuswriter",
                "instrument",
                "technique",
                "snapshot",
                "datadesc",
            ],
            "nexuswriter": {
                "devices": {},
                "instrument_info": {"name": "alba-"+self.scan.beamline, "name@short_name": self.scan.beamline},
                "masterfiles": masterfiles,
                "technique": {},
            },
            "positioners": {},  # TODO decide how to fill this (from snapshot?)
            # TODO decide how to fill this (from instruments? env var?)
            "instrument": {},
            "snapshot": snap_dict,
            "datadesc": ddesc_dict,
            "definition": "NXmonopd",
            ##################################
            # Mandatory by the schema
            ##################################
            "user_name": os.getlogin(),  # tangosys?
        }
        # Add a default curve plot
        scan_info["plots"].append(
            {"kind": "curve-plot", "items": [{"kind": "curve", "x": "epoch"}]}
        )
        validate_scan_info(scan_info)
        return scan_info

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
        self.devices: dict[str, DeviceDict] = {}
        self.devices["timer"] = DeviceDict(
            name="timer", channels=[], metadata={})
        self.devices["counters"] = DeviceDict(
            name="counters", channels=[], metadata={})
        self.devices["axis"] = DeviceDict(
            name="axis", channels=[], metadata={})

        self.acq_chain: dict[str, ChainDict] = {}
        self.channels: dict[str, ChannelDict] = {}

        # Add as metadata the full datadesc and snapshot
        snap_dict = {}
        ddesc_dict = {}
        for elem in datadesc_list:
            ddesc_dict[elem["label"]] = elem
        for elem in snapshot:
            snap_dict[elem["label"]] = elem

        self.prepare_streams(datadesc_list, header)

        scan_info = self.scan_info(snap_dict, ddesc_dict)
        self.scan.info.update(scan_info)

        self.scan.prepare()  # upload initial metadata and stream declarations

        # Scan is ready to start, eventually wait for other processes.
        # Sharing stream keys to external publishers can be done there.

        self.scan.start()

    def prepare_streams(self, datadesc_list, header):

        # declare the streams in the scan (all Numeric in our test, TODO: consider references, 1d,...)
        self.stream_list = {}
        for elem in datadesc_list:
            # if "point_nb" in elem["name"]:
            #     continue

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

            self.devices[device_type]['channels'].append(label)
            self.channels[label] = ChannelDict(device=device_type,
                                               dim=len(shape),
                                               display_name=label)

            # Check dtype and shape for the type of stream to use
            encoder = NumericStreamEncoder(dtype=dtype, shape=shape)
            scalar_stream = self.scan.create_stream(
                label, encoder, info={"unit": unit})

            # keep the list of streams for writerecord
            self.stream_list[name] = scalar_stream

        # this does the trick to have a valid acquisition chain
        self.acq_chain["axis"] = ChainDict(
            top_master="timer",
            devices=list(self.devices.keys()),
            scalars=[],
            spectra=[],
            images=[],
            master={})

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

        self.scan.info['end_time'] = datetime.datetime.now(
        ).astimezone().isoformat()
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
