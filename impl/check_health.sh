#!/bin/bash
STATE=$1
if [ $STATE = 1 ]
then
    print "health check during ACT"
else
    print "health check for SBY"
fi
