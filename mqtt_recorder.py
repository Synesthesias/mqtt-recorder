"""MQTT recorder"""

import argparse
import asyncio
import base64
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

TOPICS = ['vehicle/pose', 'vehicle/velocity', 'vehicle/pose/reliability']

logger = logging.getLogger('mqtt_recorder')


def parse_mqtt_server(server: str):
    """Parse MQTT server option into host and port."""
    if '://' in server:
        parsed = urlparse(server)
        if not parsed.hostname:
            raise ValueError("missing host in server")
        try:
            port = parsed.port or 1883
        except ValueError as exc:
            raise ValueError("invalid server format") from exc
        return parsed.hostname, port
    if ':' in server:
        host, port = server.rsplit(':', 1)
        if not host:
            raise ValueError("missing host in server")
        try:
            return host, int(port)
        except ValueError:
            raise ValueError("invalid server format") from None
    if not server:
        raise ValueError("missing host in server")
    return server, 1883


def create_mqtt_client():
    """Create a paho client without v2 deprecation warnings when available."""
    callback_api_version = getattr(mqtt, 'CallbackAPIVersion', None)
    if callback_api_version is not None:
        return mqtt.Client(callback_api_version.VERSION2)
    return mqtt.Client()


def is_successful_connection_result(rc):
    try:
        return int(rc) == 0
    except (TypeError, ValueError):
        return str(rc) == 'Success'


def sleep_until(deadline: float, busy_wait_threshold_s: float) -> None:
    """Sleep until a monotonic deadline without accumulating interval error."""
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > busy_wait_threshold_s:
            time.sleep(max(0, remaining - busy_wait_threshold_s))
        else:
            # Short waits are often rounded up by the OS timer. Busy-waiting here
            # keeps high-rate replay close to the recorded timestamps.
            pass


def start_connected_mqtt_client(host: str, port: int, keepalive: int = 5, connect_timeout_s: float = 5.0):
    """Start the paho network loop and wait until MQTT CONNACK is received."""
    connected = threading.Event()
    connection_result = {'rc': None}
    mqttc = create_mqtt_client()

    def on_connect(_client, _userdata, _flags, rc, *args):
        connection_result['rc'] = rc
        connected.set()

    mqttc.on_connect = on_connect
    connected_at = time.perf_counter()
    mqttc.connect(host, port, keepalive)
    mqttc.loop_start()
    if not connected.wait(connect_timeout_s):
        mqttc.loop_stop()
        mqttc.disconnect()
        raise TimeoutError(f"Timed out waiting for MQTT connection to {host}:{port}.")

    if not is_successful_connection_result(connection_result['rc']):
        mqttc.loop_stop()
        mqttc.disconnect()
        raise ConnectionError(f"MQTT connection to {host}:{port} failed with rc={connection_result['rc']}.")

    logger.info("Connected to MQTT broker in %.3fms", (time.perf_counter() - connected_at) * 1000)
    return mqttc


async def mqtt_record(server: str, output: str = None) -> None:
    """Record MQTT messages"""
    host, port = parse_mqtt_server(server)
    mqttc = create_mqtt_client()
    mqttc.connect(host, port, 5)
    for topic in TOPICS:
        mqttc.subscribe(topic)
    if output is not None:
        output_file = open(output, 'wt')
    else:
        output_file = sys.stdout
    def on_message(mqttc, obj, message):
        record = {
            'time': time.time(),
            'qos': message.qos,
            'retain': message.retain,
            'topic': message.topic,
            'msg_b64': base64.urlsafe_b64encode(message.payload).decode()
        }
        print(json.dumps(record), file=output_file)
    mqttc.on_message = on_message
    await mqttc.loop_forever()



async def mqtt_replay(server: str, input: str = None, delay: int = 0, realtime: bool = False, scale: float = 1,
                      busy_wait_threshold_ms: float = 1.0) -> None:
    """Replay MQTT messages"""
    host, port = parse_mqtt_server(server)
    mqttc = start_connected_mqtt_client(host, port)
    if input is not None:
        input_file = open(input, 'rt')
    else:
        input_file = sys.stdin
    if delay > 0:
        static_delay_s = delay / 1000
    else:
        static_delay_s = 0
    busy_wait_threshold_s = max(0, busy_wait_threshold_ms) / 1000
    first_record_timestamp = None
    replay_start_time = None
    previous_publish_time = None
    last_publish_info = None
    first_publish_call_time = None
    published_count = 0
    max_late_s = 0
    started_at = time.perf_counter()
    try:
        for line in input_file:
            record = json.loads(line)
            if 'msg_b64' in record:
                msg = base64.urlsafe_b64decode(record['msg_b64'].encode())
            elif 'msg' in record:
                msg = record['msg'].encode()
            else:
                logger.warning("Missing message attribute: %s", record)
                continue

            if realtime or scale != 1:
                if first_record_timestamp is None:
                    first_record_timestamp = record['time']
                    replay_start_time = time.perf_counter()
                    logger.info("Replay schedule started at record timestamp %.6f", first_record_timestamp)
                target_time = replay_start_time + (record['time'] - first_record_timestamp) * scale
                sleep_until(target_time, busy_wait_threshold_s)
                max_late_s = max(max_late_s, time.perf_counter() - target_time)
            elif static_delay_s > 0 and previous_publish_time is not None:
                sleep_until(previous_publish_time + static_delay_s, busy_wait_threshold_s)

            last_publish_info = mqttc.publish(record['topic'], msg,
                                              retain=record.get('retain'),
                                              qos=0)
            previous_publish_time = time.perf_counter()
            if first_publish_call_time is None:
                first_publish_call_time = previous_publish_time
                logger.info("First publish call after %.3fms", (first_publish_call_time - started_at) * 1000)
            published_count += 1
    finally:
        if last_publish_info is not None:
            last_publish_info.wait_for_publish()
        elapsed_s = time.perf_counter() - started_at
        logger.info("Published %d messages in %.3fs. max replay lateness: %.3fms",
                    published_count, elapsed_s, max_late_s * 1000)
        mqttc.loop_stop()
        mqttc.disconnect()


async def shutdown(sig, loop):
    loop.stop()
    os._exit(-1)


def main():
    """ Main function"""
    parser = argparse.ArgumentParser(description='MQTT recorder')

    parser.add_argument('--server',
                        dest='server',
                        metavar='server',
                        help='MQTT broker',
                        default='mqtt://127.0.0.1/')
    parser.add_argument('--mode',
                        dest='mode',
                        metavar='mode',
                        choices=['record', 'replay'],
                        help='Mode of operation (record/replay)',
                        default='record')
    parser.add_argument('--input',
                        dest='input',
                        metavar='filename',
                        help='Input file')
    parser.add_argument('--output',
                        dest='output',
                        metavar='filename',
                        help='Output file')
    parser.add_argument('--realtime',
                        dest='realtime',
                        action='store_true',
                        help="Enable realtime replay")
    parser.add_argument('--speed',
                        dest='speed',
                        type=float,
                        default=1,
                        metavar='factor',
                        help='Realtime speed factor for replay (10=10x)')
    parser.add_argument('--delay',
                        dest='delay',
                        type=int,
                        default=0,
                        metavar='milliseconds',
                        help='Delay between replayed events')
    parser.add_argument('--debug',
                        dest='debug',
                        action='store_true',
                        help="Enable debugging")
    parser.add_argument('--busy-wait-threshold-ms',
                        dest='busy_wait_threshold_ms',
                        type=float,
                        default=1.0,
                        metavar='milliseconds',
                        help='Busy-wait threshold for precise high-rate replay')

    args = parser.parse_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be > 0")

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.mode == 'replay':
        process = mqtt_replay(server=args.server, input=args.input,
                              delay=args.delay, realtime=args.realtime,
                              scale=1 / args.speed,
                              busy_wait_threshold_ms=args.busy_wait_threshold_ms)
    else:
        process = mqtt_record(server=args.server, output=args.output)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # for s in (signal.SIGINT, signal.SIGTERM):
    #     loop.add_signal_handler(s, lambda: asyncio.ensure_future(shutdown(s, loop)))

    loop.run_until_complete(process)


if __name__ == "__main__":
    main()
