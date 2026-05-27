"""Generate jittered linear vehicle pose replay data for mqtt_recorder.

The base motion matches generate_linear_vehicle_pose.py.  The generated pose
adds deterministic 2D position noise comparable to the VehicleLocalizer
mqtt_lag_test simulator.
"""

import argparse
import base64
import json
import math
import random
from pathlib import Path

from generate_linear_vehicle_pose import (
    ACCEL_DURATION,
    CRUISE_DURATION,
    DECEL_DURATION,
    START_TIME,
    TOPIC,
    make_pose_payload,
    positive_int,
    vehicle_state,
)

DEFAULT_STATIONARY_DURATION = 20.0


def jitter_offsets(rng, position_noise_mean, position_noise_stddev):
    angle = rng.uniform(0.0, 2.0 * math.pi)
    if position_noise_stddev <= 0.0:
        radius = position_noise_mean
    else:
        shape = (position_noise_mean / position_noise_stddev) ** 2
        scale = (position_noise_stddev ** 2) / position_noise_mean
        radius = rng.gammavariate(shape, scale)
    return radius * math.cos(angle), radius * math.sin(angle), 0.0


def iter_records(
    rate_hz,
    seed,
    position_noise_mean,
    position_noise_stddev,
    stationary_duration,
):
    motion_duration = ACCEL_DURATION + CRUISE_DURATION + DECEL_DURATION
    duration = motion_duration + stationary_duration
    sample_count = math.floor(duration * rate_hz) + 1
    rng = random.Random(seed)

    for index in range(sample_count):
        elapsed = min(index / rate_hz, duration)
        timestamp = START_TIME + elapsed
        motion_elapsed = min(elapsed, motion_duration)
        position_x, _speed = vehicle_state(motion_elapsed)
        jitter_x, jitter_y, jitter_z = jitter_offsets(rng, position_noise_mean, position_noise_stddev)
        payload = make_pose_payload(
            timestamp,
            position_x + jitter_x,
            jitter_y,
            jitter_z,
        )
        yield {
            "time": timestamp,
            "qos": 0,
            "retain": 0,
            "topic": TOPIC,
            "msg_b64": base64.urlsafe_b64encode(payload).decode("ascii"),
        }


def write_records(path, **kwargs):
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in iter_records(**kwargs):
            output.write(json.dumps(record, separators=(",", ":")))
            output.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("testdata"))
    parser.add_argument("--rates", type=positive_int, nargs="+", default=[10, 90])
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--position-noise-mean", type=float, default=0.0688)
    parser.add_argument("--position-noise-stddev", type=float, default=0.0694)
    parser.add_argument("--stationary-duration", type=float, default=DEFAULT_STATIONARY_DURATION)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for rate_hz in args.rates:
        path = args.output_dir / f"jitter_vehicle_pose_{rate_hz}hz.json"
        write_records(
            path,
            rate_hz=rate_hz,
            seed=args.seed,
            position_noise_mean=args.position_noise_mean,
            position_noise_stddev=args.position_noise_stddev,
            stationary_duration=args.stationary_duration,
        )
        print(path)


if __name__ == "__main__":
    main()
