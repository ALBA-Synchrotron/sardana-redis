import time
import logging
import click
import functools
import pathlib
import itertools
from blissdata.redis_engine.store import DataStore
from blissdata.redis_engine.exceptions import NoScanAvailable, EndOfStream
from blissdata.redis_engine.scan import ScanState

# Remove this as soon as we don't need compatibility with python < 3.8
try:
    cached_property = functools.cached_property
except AttributeError:
    import cached_property
    cached_property = cached_property.cached_property


FHEAD = """\
#F {filename}
#E {epoch}
"""

SHEAD = """
#S {scan_nb} {title}
#D {date}
#C Acquisition started at {date}
{motors}\
#N {nb_cols}
{oneds}\
#L {labels}
"""

SHEAD_ONED = """\
#@MCA {size}
#@CHANN {size} {first} {last} 1
#@MCA_NB {nb}
{dets}"""

STAIL = """\
#C Acquisition ended {date}
"""

SUFFIXES = {".dat", ".spec"}

DTYPES = {
    'float32', 'float64',
    'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64'
}

log = logging.getLogger(__name__)


def is_scalar(item):
    shape = item['shape']
    return not shape or shape[0] == 1


def is_1d(item):
    shape = item['shape']
    return len(shape) == 1 and shape[0] > 1


def chunks(seq, size):
    "Collect data into fixed-length chunks or blocks"
    # chunks('ABCDEFGH', 3) --> [['ABC'], ['DEF'], ['GH']]"
    return [seq[i:i + size] for i in range(0, len(seq), size)]


class SpecFile:

    def __init__(self, path, scan, max_write_interval=1):
        self.fobj = open(path, "at")
        self.scan = scan
        self.last_write_time = 0
        self.max_write_interval = max_write_interval

    def close(self):
        self.fobj.close()

    @cached_property
    def scalar_columns(self):
        return tuple(col for col in self.scan.info["datadesc"].values()
                     if col['dtype'] in DTYPES and is_scalar(col))

    @cached_property
    def scalar_labels(self):
        scalar_labels = (col["label"] for col in self.scalar_columns)
        return tuple(label.replace(" ", "_") for label in scalar_labels)

    @cached_property
    def oned_columns(self):
        return [col for col in self.scan.info["datadesc"].values()
                if col['dtype'] in DTYPES and is_1d(col)]

    @cached_property
    def oned_labels(self):
        oned_labels = (col["label"] for col in self.oned_columns)
        return tuple(label.replace(" ", "_") for label in oned_labels)

    @cached_property
    def pre_snapshot(self):
        items = self.scan.info['snapshot']
        return tuple((item["label"], item["value"]) for item in items.values()
                     if item["dtype"] in DTYPES and is_scalar(item))

    def write_file_head(self):
        data = FHEAD.format(filename=self.fobj.name, epoch=round(time.time()))
        self.fobj.write(data)

    def write_scan_head(self):
        meta = self.scan.info
        oneds = self.oned_columns
        if self.pre_snapshot:
            O, P = [], []
            for i, chunk in enumerate(chunks(self.pre_snapshot, 8)):
                O.append("#O{} ".format(i) + "  ".join(i[0] for i in chunk))
                P.append("#P{} ".format(i) +
                         " ".join(str(i[1]) for i in chunk))
            motors = "\n".join(O + P) + "\n"
        else:
            motors = ""
        if oneds:
            dets = ("#@DET_{} {}".format(i, label)
                    for i, label in enumerate(self.oned_labels))
            size = oneds[-1]["shape"][0]
            oneds = SHEAD_ONED.format(
                size=size,
                first=0,
                last=size - 1,
                nb=len(oneds),
                dets="\n".join(dets)
            ) + "\n"
        else:
            oneds = ""
        scalar_labels = self.scalar_labels
        data = SHEAD.format(
            scan_nb=meta["scan_nb"],
            title=meta["title"],
            date=meta["start_time"],
            motors=motors,
            nb_cols=len(scalar_labels),
            labels="  ".join(scalar_labels),
            oneds=oneds
        )
        self.fobj.write(data)

        # TODO: Write UVAR here

        self.fobj.flush()

    def write_scan_tail(self):
        # just in case there are pending points
        self._write_scan_points()
        self.fobj.write(STAIL.format(date=self.scan.info["end_time"]))
        self.fobj.flush()

    def write_scan_points(self):
        now = time.monotonic()
        if (now - self.last_write_time) < self.max_write_interval:
            return
        self._write_scan_points()
        self.last_write_time = now

    def _write_scan_points(self):
        
        indSc = []
        valuesSc = []
        ind1D = []
        values1D = []

        # is this done like this for ordering and efficiency?
        for col in self.scalar_columns:
            try:
                val = self.cursors[col["label"]].read()
            except EndOfStream:
                log.warning(
                    "End of stream for scalar column {}".format(col["label"]))
                return
            indSc.append(val[0])  # not used by now
            valuesSc.append(val[1])
        for col in self.oned_columns:
            try:
                val = self.cursors[col["label"]].read()
            except EndOfStream:
                log.warning(
                    "End of stream for 1D column {}".format(col["label"]))
                return
            ind1D.append(val[0])  # not used by now
            values1D.append(val[1])

        # TODO check the nr of points is consistent everywhere
        npoints = len(valuesSc[0])
        if npoints != len(values1D[0]):
            log.warning("Number of points between stream cursors do not match")

        lines = []
        for i in range(npoints):
            oneds = (chan1D[i] for chan1D in values1D)
            # transform each 1D in a list of strings ("@A", v0, ..., vn-1)
            oneds = (map(str, itertools.chain(("@A",), oned))
                     for oned in oneds)
            lines += (" ".join(oned) for oned in oneds)
            values = (chanSc[i] for chanSc in valuesSc)
            lines.append(" ".join(map(str, values)))

        self.fobj.write("\n".join(lines))
        self.fobj.write("\n")
        self.fobj.flush()

    def prepareCursors(self):
        self.cursors = {}
        for key, stream in self.scan.streams.items():
            self.cursors[key] = stream.cursor()


def open_spec_file(scan) -> SpecFile:
    filename = pathlib.Path(scan.info["filename"])
    if filename.suffix not in SUFFIXES:
        return None
    exists = filename.exists()
    directory = filename.parent
    if not directory.is_dir():
        directory.mkdir(parents=True)
    fobj = SpecFile(filename, scan)
    if not exists:
        log.info("new file!")
        fobj.write_file_head()
    return fobj


def process_scan(scan) -> None:
    print(f"Processing scan {scan.key}")

    while scan.state < ScanState.PREPARED:
        scan.update()

    fobj = open_spec_file(scan)
    if fobj is None:
        log.info("no spec file in scan")
    else:
        log.info("recording into %r", fobj.fobj.name)
        fobj.write_scan_head()

    fobj.prepareCursors()  # to read the data

    while scan.state < ScanState.STOPPED:
        scan.update(block=False)
        # wait for the scan to finish, here we will write the spec file
        fobj.write_scan_points()

    while scan.state < ScanState.CLOSED:
        # waiting for CLOSED to upload final metadata
        scan.update()

    fobj.write_scan_tail()
    fobj.close()
    log.info("finished recording to %r", fobj.fobj.name)


class SpecWriterService():

    def __init__(self, redis_url, log_level, next_scan_timeout):
        self.running = False
        self.next_scan_timeout = next_scan_timeout
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        log.info("Connecting to DB")
        self.data_store = DataStore(redis_url)

    def start(self):
        self.running = True
        timestamp = None
        log.info("Waiting for scan")
        while self.running:
            try:
                timestamp, key = self.data_store.get_next_scan(
                    since=timestamp, timeout=self.next_scan_timeout)
            except NoScanAvailable:
                continue
            scan = self.data_store.load_scan(key)
            process_scan(scan)
            log.info("Waiting for next scan")

    def get_status(self):
        status = "is RUNNING" if self.running else "is STOPPED"
        return 'SpecWriter {}'.format(status)

    def stop(self):
        self.running = False


@click.command()
@click.argument('redis_url', default='redis://localhost:6379')
@click.option(
    "--log-level", default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
)
@click.option(
    "--scan-timeout", default="0", type=int
)
def main(redis_url, log_level, scan_timeout):
    SpecWriterService(redis_url, log_level, scan_timeout).start()


if __name__ == '__main__':
    main()
