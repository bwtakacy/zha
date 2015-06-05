rm -f /var/lib/pgsql/9.4/data/postgresql.conf
ln -s /var/lib/pgsql/9.4/data/postgresql.conf.clustered /var/lib/pgsql/9.4/data/postgresql.conf
/usr/pgsql-9.4/bin/psql -c "select pg_reload_conf()"
