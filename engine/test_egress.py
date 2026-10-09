"""Run: uv run python test_egress.py  (no models loaded). Parses saved nettop / netstat samples; loopback must drop out."""
from server import parse_netstat, parse_nettop

NETTOP = """,bytes_in,bytes_out,
python3.12.85989,0,0,
tcp4 127.0.0.1:8765<->*:*,,,
tcp4 127.0.0.1:8765<->127.0.0.1:61234,900,51234,
tcp6 ::1.8765<->::1.61235,10,20,
tcp6 fe80::1%lo0.8765<->fe80::1%lo0.5000,1,2,
udp4 *:*<->*:*,,,
udp4 *:58941<->*:*,0,1038,
tcp4 192.168.0.243:59769<->163.70.131.11:443,28153222,36251177,
tcp6 2001:db8::5.50000<->2606:4700::1.443,5,7,
"""
assert parse_nettop(NETTOP) == {"udp4 *:58941<->*:*": 1038, "tcp4 192.168.0.243:59769<->163.70.131.11:443": 36251177,
                                "tcp6 2001:db8::5.50000<->2606:4700::1.443": 7}, parse_nettop(NETTOP)
assert parse_nettop(NETTOP.split("udp4 *:5")[0]) == {}  # the engine's real sample: loopback only -> nothing

NETSTAT = """Name       Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll
lo0        16384 <Link#1>                      45930615     0 377133719540 45930615     0 377133719540     0
lo0        16384 127           localhost       45930615     - 377133719540 45930615     - 377133719540     -
en0        1500  <Link#14>   aa:bb:cc:dd:ee:ff  1000     0     500000      900     0     300000     0
en0        1500  192.168.0     192.168.0.243      1000     -     500000      900     -     300000     -
utun0      1500  <Link#18>                            0     0          0        1     0         80     0
utun0      1500  miguels-mac fe80:12::8a41:372        0     -          0        1     -         80     -
"""
assert parse_netstat(NETSTAT) == 300080, parse_netstat(NETSTAT)
print("ok")
