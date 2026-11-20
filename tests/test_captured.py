"""Status replies (42H) captured from a 16S200A board (hardware T1_G, firmware 01.00.01)."""

import pytest

from daren2mqtt.decode import Kind, decode_analog
from daren2mqtt.protocol import ProtocolError, decode

CAPTURED = [
    # charging at 100 %, cell 16 balancing
    "~22014A00E0C60027101532100D2B0D2C0D2A0D290D2C0D2A0D2B0D2C0D2A0D2A0D2E0D2B0D2D0D2B0D2C0E6E0122011801220401180122012201220077000000610157C357C300DA011000010000000100230000000000000000800000000000000000000000000000D4FD",
    # charging at 4.12 %
    "~22014A00E0C600019C140D100C6A0C840C5B0C950C9C0C8C0C8C0C820C890C830C8B0CA30C990C8E0C8C0C830136013601360401360136013601360574000000600156D9039600DA000000010000008000230000000000000000000000000000000000000000000000D4E0",
    # charging at 6.35 %
    "~22014A00E0C600027B144B100CA20CB40CA70CB60CAC0CB40CAC0CBE0CAB0CB30CAB0CB70CAD0CB40CAA0CAF012C013601360401360136013601360892000000600156D9058600DA000000010000008000230000000000000000000000000000000000000000000000D43D",
    # charging at 13.59 %
    "~22014A00E0C600054F1471100CC80CC40CBD0CC90CCD0CC60CC70CC80CC70CC40CC60CD00CCC0CC60CC70CC001360136013604013601360136013606C9000000600156D90BCE00DA000000010000008000230000000000000000000000000000000000000000000000D440",
    # discharging at 3.8 %
    "~22014A00E0C600017C1327100BE30BE90BA40C070C2B0BF90C030BD00BF70BE70BFC0C340C190C000C000BF5012C01360136040136013601400140F7D1000000610157C3035600DA000000020000008000230000000000000000000000000000000000000000000000D4F4",
    # discharging at 2.97 %
    "~22014A00E0C600012912DA100B970BB40B640BD60C0D0BC50BDE0B8F0BD00BAF0BD50C0D0BF90BCE0BDA0BC1012C01360136040136013601400140F787000000610157C3029D00DA000000020000008000230000000000000000000000000000000000000000000000D467",
    # discharging at 1.92 %
    "~22014A00E0C60000C01266100B450B650AE00B990BD90B810B9B0B380B880B5F0B8D0BE00BBD0B8D0B930B7C013601400136040140014001400140F808000000610157C301B100DA000000020000008000230000000000000000000000000000000000000000000000D502",
    # empty: cell undervoltage protection has turned the discharge MOSFET off
    "~22014A00E0C600000011E3100AB20B1909D30B630BAB0B400B5C0AE00B430B0D0B4A0BBE0B8A0B510B4F0B38012C014001360401400140014001400000000000600156D9000000DA01A200000000008100210000000000000000000000000000000000000000000000D54A",
    # a bit error turned the temperature sensor count 04 into 44
    "~22014A00E0C6001EF614D6100D0F0D040D040D070D070D060D040D060D070D070D040D070D040D060D070D0401220122012C440122012201220122FBF9000000600156D944D600E0000000020000000000230000000000000000000000000000000000000000000000D570",
]
FULL, *LOW, EMPTY, BIT_ERROR = CAPTURED


def analog(frame: str):
    return decode_analog(decode(frame.encode() + b"\r").info)


def test_full_and_balancing():
    a = analog(FULL)
    assert a.soc == pytest.approx(100.0) and a.voltage == pytest.approx(54.26)
    assert a.current == pytest.approx(1.19) and a.state == "charging"
    assert a.charge_mos and a.discharge_mos
    assert a.cell_min == (3369, 4) and a.cell_max == (3694, 16)
    assert (a.temp_ambient, a.temp_pack, a.temp_mos) == pytest.approx((29.0, 28.0, 29.0))
    assert a.temp_sensors == pytest.approx((28.0, 29.0, 29.0, 29.0))
    assert a.soh == 97 and a.cycles == 218
    assert a.full_ah == pytest.approx(224.67) and a.remaining_ah == pytest.approx(224.67)
    assert a.balancing_cells == [16]
    assert a.flags(Kind.ALARM) == ["cell high voltage", "cell voltage difference"]
    assert a.flags(Kind.PROTECTION) == [] and a.flags(Kind.FAULT) == []


@pytest.mark.parametrize(
    ("frame", "soc", "current", "state"),
    [
        (LOW[0], 4.12, 13.96, "charging"),
        (LOW[1], 6.35, 21.94, "charging"),
        (LOW[2], 13.59, 17.37, "charging"),
        (LOW[3], 3.8, -20.95, "discharging"),
        (LOW[4], 2.97, -21.69, "discharging"),
        (LOW[5], 1.92, -20.4, "discharging"),
    ],
)
def test_low_charge(frame, soc, current, state):
    a = analog(frame)
    assert a.soc == pytest.approx(soc) and a.current == pytest.approx(current) and a.state == state
    assert a.flags(Kind.ALARM) == ["low state of charge"]


def test_empty_with_undervoltage_protection():
    a = analog(EMPTY)
    assert a.soc == 0 and a.remaining_ah == 0 and a.voltage == pytest.approx(45.79)
    assert a.state == "idle" and a.charge_mos and not a.discharge_mos
    assert a.cell_min == (2515, 3)
    assert a.flags(Kind.PROTECTION) == ["cell undervoltage"]
    assert a.flags(Kind.ALARM) == [
        "cell low voltage",
        "pack low voltage",
        "cell voltage difference",
        "low state of charge",
    ]


def test_bit_error_fails_the_checksum():
    with pytest.raises(ProtocolError, match="checksum mismatch"):
        decode(BIT_ERROR.encode() + b"\r")
