rm -f /home/postgres/pg_data/9.4/postgresql.conf
ln -s /home/postgres/pg_data/9.4/postgresql.conf.standalone /home/postgres/pg_data/9.4/postgresql.conf
/usr/local/pgsql/9.4/bin/psql -c "select pg_reload_conf()"
