"""Generate linear vehicle pose replay data for mqtt_recorder."""
""""テストデータとして、車両が直線運動で加速→速度維持→減速するときのMQTTデータを作成します。"""

import argparse
import base64
import json
import math
import struct
from pathlib import Path


START_TIME = 1_700_000_000.0
ACCEL_DURATION = 10.0
CRUISE_DURATION = 5.0
DECEL_DURATION = 10.0
MAX_SPEED = 40.0
TOPIC = "vehicle/pose"
TYPE_DOUBLE = 0x01
TYPE_DOCUMENT = 0x03
TYPE_INT32 = 0x10
TYPE_INT64 = 0x12
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def bson_cstring(value):
    return value.encode("utf-8") + b"\x00"


def bson_document(value):
    """Serialize testdata-only BSON values: dict, float, and signed ints."""
    body = bytearray()
    for key, item in value.items():
        if isinstance(item, dict):
            body.append(TYPE_DOCUMENT)
            body.extend(bson_cstring(key))
            body.extend(bson_document(item))
        elif isinstance(item, float):
            body.append(TYPE_DOUBLE)
            body.extend(bson_cstring(key))
            body.extend(struct.pack("<d", item))
        elif isinstance(item, int):
            if INT32_MIN <= item <= INT32_MAX:
                body.append(TYPE_INT32)
                body.extend(bson_cstring(key))
                body.extend(struct.pack("<i", item))
            elif INT64_MIN <= item <= INT64_MAX:
                body.append(TYPE_INT64)
                body.extend(bson_cstring(key))
                body.extend(struct.pack("<q", item))
            else:
                raise TypeError(f"BSON int out of int64 range for {key}: {item}")
        else:
            raise TypeError(f"Unsupported BSON value for {key}: {type(item)}")

    total_length = len(body) + 5
    return struct.pack("<i", total_length) + bytes(body) + b"\x00"


def vehicle_state(time_s: float) -> tuple[float, float]:
    """Return linear motion position (m) and speed (m/s) at time_s seconds.

    Motion phases use MAX_SPEED, ACCEL_DURATION, CRUISE_DURATION, and
    DECEL_DURATION.
    """
    accel = MAX_SPEED / ACCEL_DURATION
    cruise_start_x = 0.5 * accel * ACCEL_DURATION * ACCEL_DURATION
    decel_start_x = cruise_start_x + MAX_SPEED * CRUISE_DURATION

    if time_s <= ACCEL_DURATION:
        speed = accel * time_s
        position = 0.5 * accel * time_s * time_s
    elif time_s <= ACCEL_DURATION + CRUISE_DURATION:
        dt = time_s - ACCEL_DURATION
        speed = MAX_SPEED
        position = cruise_start_x + MAX_SPEED * dt
    else:
        dt = min(time_s - ACCEL_DURATION - CRUISE_DURATION, DECEL_DURATION)
        speed = max(0.0, MAX_SPEED - accel * dt)
        position = decel_start_x + MAX_SPEED * dt - 0.5 * accel * dt * dt

    return position, speed


def make_pose_payload(timestamp, position_x):
    message = {
        "timestamp": timestamp,
        "data": {
            "position": {
                "x": position_x,
                "y": 0.0,
                "z": 0.0,
            },
            "rotation": {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "w": 1.0,
            },
        },
    }
    return bson_document(message)


def iter_records(rate_hz):
    duration = ACCEL_DURATION + CRUISE_DURATION + DECEL_DURATION
    sample_count = math.floor(duration * rate_hz) + 1
    for index in range(sample_count):
        elapsed = min(index / rate_hz, duration)
        timestamp = START_TIME + elapsed
        position_x, _speed = vehicle_state(elapsed)
        payload = make_pose_payload(timestamp, position_x)
        yield {
            "time": timestamp,
            "qos": 0,
            "retain": 0,
            "topic": TOPIC,
            "msg_b64": base64.urlsafe_b64encode(payload).decode("ascii"),
        }


def write_records(path, rate_hz):
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in iter_records(rate_hz):
            output.write(json.dumps(record, separators=(",", ":")))
            output.write("\n")


def positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("testdata"))
    parser.add_argument("--rates", type=positive_int, nargs="+", default=[90, 900])
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for rate_hz in args.rates:
        path = args.output_dir / f"linear_vehicle_pose_{rate_hz}hz.json"
        write_records(path, rate_hz)
        print(path)


if __name__ == "__main__":
    main()
