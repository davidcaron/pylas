import numpy as np

from .errors import LazPerfNotFound
from .pointdimensions import get_dtype_of_format_id

HAS_LAZPERF = False

try:
    import lazperf

    HAS_LAZPERF = True
except ModuleNotFoundError:
    HAS_LAZPERF = False

schema = [
    {u'type': u'signed', u'name': u'X', u'size': 4},
    {u'type': u'signed', u'name': u'Y', u'size': 4},
    {u'type': u'signed', u'name': u'Z', u'size': 4},
    {u'type': u'unsigned', u'name': u'Intensity', u'size': 2},
    {u'type': u'unsigned', u'name': u'BitFields', u'size': 1},
    {u'type': u'unsigned', u'name': u'Classification', u'size': 1},
    {u'type': u'signed', u'name': u'ScanAngleRank', u'size': 1},
    {u'type': u'unsigned', u'name': u'UserData', u'size': 1},
    {u'type': u'unsigned', u'name': u'PointSourceId', u'size': 2},
    {u'type': u'floating', u'name': u'GpsTime', u'size': 8},
    {u'type': u'unsigned', u'name': u'Red', u'size': 2},
    {u'type': u'unsigned', u'name': u'Green', u'size': 2},
    {u'type': u'unsigned', u'name': u'Blue', u'size': 2},
]


def raise_if_no_lazperf():
    if not HAS_LAZPERF:
        raise LazPerfNotFound('Lazperf not found, cannot manipulate laz data')


def is_point_format_compressed(point_format_id):
    try:
        compression_bit_7 = (point_format_id & 0x80) >> 7
        compression_bit_6 = (point_format_id & 0x40) >> 6
        if not compression_bit_6 and compression_bit_7:
            return True
    except ValueError:
        pass
    return False


def compressed_id_to_uncompressed(point_format_id):
    return point_format_id & 0x3f

def decompress_stream(compressed_stream, point_format_id, point_count, laszip_vlr):
    raise_if_no_lazperf()

    ndtype = get_dtype_of_format_id(point_format_id)
    point_compressed = np.frombuffer(compressed_stream.read(), dtype=np.uint8)

    # print('point compressed size:', point_compressed.shape)
    vlr_data = np.frombuffer(laszip_vlr.record_data, dtype=np.uint8)
    decompressor = lazperf.VLRDecompressor(point_compressed, vlr_data)
    # point_buffer = np.zeros((ndtype.itemsize,), dtype=np.uint8)
    # point_uncompressed = np.zeros(point_count * ndtype.itemsize, dtype=np.uint8)
    # begin, point_size = 0, ndtype.itemsize
    # for _ in range(point_count):
    #     decompressor.decompress(point_buffer)
    #     end = begin + point_size
    #     point_uncompressed[begin:end] = point_buffer
    #     begin = end

    print('size:', len(laszip_vlr.record_data))
    point_uncompressed = decompressor.decompress_points(point_count)

    point_uncompressed = np.frombuffer(point_uncompressed, dtype=ndtype)
    print(point_uncompressed.shape)

    return point_uncompressed


def compress_buffer(uncompressed_buffer, point_format_id, point_count):
    raise_if_no_lazperf()
    import json
    assert sum(dim['size'] for dim in schema) == 34

    compressor = lazperf.Compressor(json.dumps(schema))
    uncompressed_buffer = np.frombuffer(uncompressed_buffer, dtype=np.uint8)
    compressed = compressor.compress(uncompressed_buffer)
    return compressed
