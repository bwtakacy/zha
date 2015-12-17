rm -f /var/lib/pgsql/9.4/data/postgresql.conf
ln -s /var/lib/pgsql/9.4/data/postgresql.conf.standalone /var/lib/pgsql/9.4/data/postgresql.conf
/usr/pgsql-9.4/bin/psql -c "select pg_reload_conf()" 2> /dev/null
