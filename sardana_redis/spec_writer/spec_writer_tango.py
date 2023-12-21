import threading
from tango import DevState
from tango.server import Device, command, device_property
from sardana_redis.spec_writer.spec_writer_service import SpecWriterService


class SpecWriter(Device):

    spec_writer_service = None

    redis_url = device_property(
        dtype=str, default_value='redis://localhost:6379')
    log_level = device_property(dtype=str, default_value='INFO')
    next_scan_timeout = device_property(dtype=int, default_value=2)

    def init_device(self):
        Device.init_device(self)
        self.info_stream('Initializing device...')
        self.spec_writer_service = SpecWriterService(
            self.redis_url, self.log_level, self.next_scan_timeout)
        self.start()

    def dev_status(self):
        return self.spec_writer_service.get_status()

    @command
    def start(self):
        self.thread = threading.Thread(target=self.spec_writer_service.start)
        self.thread.start()
        self.set_state(DevState.ON)

    @command
    def stop(self):
        self.spec_writer_service.stop()
        self.thread.join()
        self.set_state(DevState.OFF)


if __name__ == "__main__":
    SpecWriter.run_server()
