/usr/pgsql-9.4/bin/pg_ctl -D /var/lib/pgsql/9.4/data/ promote
sudo ip addr add 192.168.0.10/24 dev eth0
sudo arping 192.168.0.10 -I eth0 -c 3
