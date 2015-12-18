pg_ctl -D ${PGDATA} promote
sudo ip addr add 172.27.104.212/16 dev eth0
sudo arping 172.27.104.212 -I eth0 -c 3
