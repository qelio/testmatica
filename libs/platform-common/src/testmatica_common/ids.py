import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """UUID версии 7 (RFC 9562): первые 48 бит — время в мс, поэтому id сортируются по времени."""
    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 случайных бит
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= ((rand >> 68) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand & ((1 << 62) - 1)
    return uuid.UUID(int=value)
