#!/bin/sh
# This script calls influxillant for the previous year.
# To be executed once a day during the first week of the year. 
previous_year=$(echo $(($(date +%Y) - 1)))
/usr/local/bin/python3.13 /app/vaillant2influx.py --year $previous_year
