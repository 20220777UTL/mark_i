"""Reset LOCAL grSim to blue 1/2 versus yellow 0, using official replacement protocol.

Protocol source: https://github.com/RoboCup-SSL/grSim/tree/master/src/proto
No third-party protobuf dependency is required for this small write-only packet.
Positions in this wire protocol are metres; directions are degrees.
"""
import argparse
import socket
import struct


def varint(n):
    data = bytearray()
    while n > 127:
        data.append((n & 127) | 128)
        n >>= 7
    data.append(n)
    return bytes(data)


def message(field, value):
    return varint(field*8+2) + varint(len(value)) + value


def number(field, value):
    return varint(field*8+1) + struct.pack("<d", value)


def integer(field, value):
    return varint(field*8) + varint(int(value))


def scene(ball_x=1.8, ball_y=.55, swap_robots=False):
    ball = b"".join(number(n, v) for n, v in enumerate((ball_x, ball_y, 0, 0), 1))
    packet = message(1, ball)
    active = {(False, 1): (ball_x-.3, ball_y, 0),
              (False, 2): (min(3.0, ball_x+.4), -.85, 0), (True, 0): (4.25, 0, 180)}
    if swap_robots:
        active[(False, 1)], active[(False, 2)] = active[(False, 2)], active[(False, 1)]
    for yellow in (False, True):
        for rid in range(16):
            enabled = (yellow, rid) in active
            x, y, angle = active.get((yellow, rid), (-4.7, -3.5-rid*.2, 0))
            robot = number(1, x)+number(2, y)+number(3, angle)+integer(4, rid)+integer(5, yellow)+integer(6, enabled)
            packet += message(2, robot)
    return message(2, packet)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ball-x", type=float, default=1.8)
    parser.add_argument("--ball-y", type=float, default=.55)
    parser.add_argument("--swap-robots", action="store_true", help="Swap blue 1/2 starting positions")
    args = parser.parse_args()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(scene(args.ball_x, args.ball_y, args.swap_robots), ("127.0.0.1", 20011))
    print("Reset local grSim: blue 1/2, yellow practice keeper 0")
