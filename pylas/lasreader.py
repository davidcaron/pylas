import io
import logging
import struct

from . import headers, errors, evlr
from .compression import laszip_decompress
from .lasdatas import las14, las12
from .point import dims, record
from .vlrs import rawvlr
from .vlrs.vlrlist import VLRList


class LasReader:
    def __init__(self, stream, closefd=True):
        self.start_pos = stream.tell()
        self._check_file_signature(stream)
        self.stream = stream
        self.closefd = closefd
        self.header = self.read_header()

    @staticmethod
    def _check_file_signature(stream):
        """ Reads the 4 first bytes of the stream to check that is LASF"""
        file_sig = stream.read(len(headers.LAS_FILE_SIGNATURE))
        if file_sig != headers.LAS_FILE_SIGNATURE:
            raise ValueError('File Signature ({}) is not {}'.format(
                file_sig, headers.LAS_FILE_SIGNATURE
            ))

    def read_header(self):
        """ Reads the head of the las file, or if it has already been read,
        returns it

        raises ValueError if the file signature field is not the expected one
        """
        self.stream.seek(self.start_pos)
        header = headers.HeaderFactory().read_from_stream(self.stream)
        return header

    def read_vlrs(self):
        """ Reads and return the vlrs of the file
        """
        self.stream.seek(self.start_pos + self.header.header_size)
        return VLRList.read_from(self.stream, num_to_read=self.header.number_of_vlr)

    def read(self):
        """ Reads the whole las data (header, vlrs ,points, etc) and returns a LasData
        object
        """
        vlrs = self.read_vlrs()
        self._warn_if_not_at_expected_pos(self.header.offset_to_point_data, "end of vlrs", "start of points")
        self.stream.seek(self.start_pos + self.header.offset_to_point_data)

        try:
            points = self._read_points(vlrs)
        except (RuntimeError, errors.LazPerfNotFound) as e:
            logging.error("LazPerf failed to decompress ({}), trying laszip.".format(e))
            self.stream.seek(self.start_pos)
            self.__init__(io.BytesIO(laszip_decompress(self.stream)))
            return self.read()

        if dims.format_has_waveform_packet(self.header.point_data_format_id):
            self.stream.seek(self.start_pos + self.header.start_of_first_waveform_data_packet)
            if self.header.global_encoding.are_waveform_flag_equal():
                raise ValueError(
                    'Incoherent values for internal and external waveform flags, both are {})'.format(
                        'set' if self.header.global_encoding.waveform_internal else 'unset'
                    ))
            if self.header.global_encoding.waveform_internal:
                # TODO: Find out what to do with these
                _, _ = self._read_internal_waveform_packet()
            elif self.header.global_encoding.waveform_external:
                logging.info("Waveform data is in an external file, you'll have to load it yourself")

        if self.header.version >= '1.4':
            evlrs = self.read_evlrs()
            return las14.LasData(header=self.header, vlrs=vlrs, points=points, evlrs=evlrs)

        return las12.LasData(header=self.header, vlrs=vlrs, points=points)

    def _read_points(self, vlrs):
        """ private function to handle reading of the points record parts
        of the las file.

        the header is needed for the point format and number of points
        the vlrs are need to get the potential laszip vlr as well as the extra bytes vlr
        """
        try:
            extra_dims = vlrs.get('ExtraBytesVlr')[0].type_of_extra_dims()
        except IndexError:
            extra_dims = None

        if self.header.are_points_compressed:
            laszip_vlr = vlrs.pop(vlrs.index('LasZipVlr'))
            points = self._read_compressed_points_data(laszip_vlr)
        else:
            points = record.PackedPointRecord.from_stream(
                self.stream,
                self.header.point_data_format_id,
                self.header.number_of_point_records,
                extra_dims
            )
        return points

    def _read_compressed_points_data(self, laszip_vlr):
        """ reads the compressed point record
        """
        offset_to_chunk_table = struct.unpack('<q', self.stream.read(8))[0]
        size_of_point_data = offset_to_chunk_table - self.stream.tell()

        if offset_to_chunk_table <= 0:
            logging.warning("Strange offset to chunk table: {}, ignoring it..".format(
                offset_to_chunk_table))
            size_of_point_data = -1  # Read everything

        points = record.PackedPointRecord.from_compressed_buffer(
            self.stream.read(size_of_point_data),
            self.header.point_data_format_id,
            self.header.number_of_point_records,
            laszip_vlr
        )
        return points

    def _read_internal_waveform_packet(self):
        """ reads and returns the waveform vlr header, waveform record
        """
        # This is strange, the spec says, waveform data packet is in a EVLR
        #  but in the 2 samples I have its a VLR
        # but also the 2 samples have a wrong user_id (LAS_Spec instead of LASF_Spec)
        b = bytearray(self.stream.read(rawvlr.VLR_HEADER_SIZE))
        waveform_header = rawvlr.VLRHeader.from_buffer(b)
        waveform_record = self.stream.read()
        logging.info(waveform_header.user_id, waveform_header.record_id,
                     waveform_header.record_length_after_header)
        logging.debug("Read: {} MBytes of waveform_record".format(
            len(waveform_record) / 10 ** 6))

        return waveform_header, waveform_record

    def read_evlrs(self):
        self.stream.seek(self.start_pos + self.header.start_of_first_evlr)
        return [evlr.RawEVLR.read_from(self.stream) for _ in range(self.header.number_of_evlr)]

    def _warn_if_not_at_expected_pos(self, expected_pos, end_of, start_of):
        """ Helper function to warn about unknown bytes found in the file"""
        diff = expected_pos - self.stream.tell()
        if diff != 0:
            logging.warning("There are {} bytes between {} and {}".format(diff, end_of, start_of))

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.closefd:
            self.close()