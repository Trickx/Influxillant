#!/usr/bin/env python3

import asyncio
import logging
import re
#from xml.etree.ElementTree import tostring

import configargparse
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import date
from myPyllant.api import MyPyllantAPI
import datetime
from dateutil import tz
import dateutil.parser

parser = configargparse.ArgParser()
parser.add_argument(
    '-y', "--year", help="Year of the report, defaults to current year", type=int,
    default=date.today().year, env_var='V2I_YEAR', required=False
)
parser.add_argument(
    '-a', "--account", help="Vaillant user account, typically your e@mail",
    env_var='V2I_ACCOUNT', required=True
)
parser.add_argument(
    '-p', "--password", help="Your Vaillant password",
    env_var='V2I_PASSWORD', required=True
)
parser.add_argument(
    '-d', "--devicebrand", help="Your heating device brand, defaults to vaillant",
    env_var='V2I_DEVICEBRAND', default="vaillant", required=False
)
parser.add_argument(
    '-c', "--country", help="Your location country, defaults to germany",
    env_var='V2I_COUNTRY', default="germany", required=False
)
parser.add_argument(
    '-b', "--bucket", help="InfluxDB bucket to write into",
    env_var='V2I_BUCKET', required=True
)
parser.add_argument(
    '-m', "--measurement", help="InfluxDB measurement to write into, default to device name",
    env_var='V2I_MEASUREMENT', required=False
)
parser.add_argument(
    '-o', "--org", help="InfluxDB organisation",
    env_var='V2I_ORG', required=True
)
parser.add_argument(
    '-t', "--token", help="InfluxDB bucket access token",
    env_var='V2I_TOKEN', required=True
)
parser.add_argument(
    '-u', "--url", help="InfluxDB URL, defaults to \"http:localhost:8086\"",
    env_var='V2I_URL', default="http:localhost:8086", required=False
)
parser.add_argument(
    '-l', "--loglevel", help="Log Level, defaults to INFO, options: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    env_var='V2I_LOGLEVEL', default="INFO", required=False
)
parser.add_argument(
    '-w', "--writeresults", help="Write results into InfluxDB, defaults to True",
    env_var='V2I_WRITE', default=True, required=False
)
parser.add_argument(
    '-tz', "--timezone", help="Timezone e.g. Europe/Berlin, defaults to UTC",
    env_var='V2I_TIMEZONE', default="UTC", required=False
)
parser.add_argument(
    '-to', "--timeoffset", help="Time offset which is added to timestamp e.g. 23:59:59 [hh:mm:ss]",
    env_var='V2I_TIMEOFFSET', default="00:00:00", required=False
)

async def main(bucket, org, token, url, account, password, devicebrand, year: int, country=None, writeresults=True, measurement=None, timezone="UTC", timeoffset="00:00:00"):
    #logging.StreamHandler.terminator = ""
    #logger = logging.getLogger("vaillant2influx")
    logger = logging.getLogger(" ")

    # Prepare Timezone
    logger.info(f"Timezone: {timezone}")
    tzinfos = {"XYZ": tz.gettz(timezone)}

    # Prepare writeresults
    if writeresults == "False":
        writeresults = False
        logger.info(f"Writing to InfluxDB has been disabled.")

    # Prepare Time Offset
    logger.info(f"Timeoffset: {timeoffset}")
    _hours, _mins, _secs = timeoffset.split(":")
    hours = int(_hours)
    mins = int(_mins)
    secs = int(_secs)
    deltatime = datetime.timedelta(seconds=secs, minutes=mins, hours=hours)

    async with (MyPyllantAPI(account, password, devicebrand, country) as api):
        logger.info("Getting systems...")
        #logger.info("Getting systems...")
        system_count = 1
        async for system in api.get_systems():
            logger.info(f"Fetching reports of system #{system_count} {system.home.home_name} {system.system_name} for the year {year} ...")
            reports = api.get_yearly_reports(system, year)
            system_count = system_count + 1
            report_count = 0
            async for report in reports:
                report_count = report_count + 1
                logger.info(f"Parsing report #{report_count}")
                logger.info(f"Report.file_name: {report.file_name}")
                #logger.info(f"Report.extra_fields: {report.extra_fields}\n")
                #logger.debug(f"Report.file_content: {report.file_content}\n")

                #'energy_data_2025_FlexothermExclusive_12345612345123451234512345N5.csv'
                device: str
                _enerygy,_data,_year,device,serial,_ext = report.file_name.replace('.', '_').split("_")
                logger.info(f"Seriennumer: {serial}")
                logger.info(f"Gerätename: {device}")

                # Replace ":" by "_"
                content = report.file_content
                content = re.sub(':Cooling', '_Cooling', content)
                content = re.sub(':Heating', '_Heating', content)
                content = re.sub(':DomesticHotWater', '_DomesticHotWater', content)

                lines = content.splitlines()
                logger.info(f"Der Report enthält {len(lines)} Zeilen")

                #Read Header
                logger.info(f"# Header #")
                logger.info(f"Header #1: {lines.pop(0)}")
                logger.info(f"Header #2: {lines.pop(0)}")

                # Parse Columns
                logger.info(f"# Spalten (Messreihen) #")
                columns = lines.pop(0).split(';')

                logger.info(f"Anzahl Spalten detektiert: {len(columns)}")
                logger.info(f"Spalten: {columns}")

                #Anzahl Tageswerte
                anfang = lines[0].split(";")
                ende = lines[len(lines)-1].split(";")
                logger.info(f"{len(lines)-3} Tageswerte im Bereich {anfang[0].partition(' ')[0]} bis {ende[0].partition(' ')[0]}")

                #Prepare InfluxDB data points
                points = []

                # Measurement if not given device name is used
                if not measurement:
                    #measurement = system.system_name.partition(' ')[0]
                    measurement = device
                logger.info(f"Measurement: {measurement}")

                # Home-Tag
                home = system.home.home_name
                logger.info(f"Home: {home}")

                for line in lines:
                    logger.debug(f"Line: {line}")
                    splittedline = line.split(";")

                    # Timestamp
                    timestamp = splittedline[0]

                    # Timestamp Adjustements
                    # Timezone, Offset
                    # List of timezone: https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568
                    utctime = dateutil.parser.parse(timestamp + " XYZ", tzinfos=tzinfos)

                    # Time Offset
                    utctime = utctime + deltatime

                    for col in range(1, len(columns)):
                        value = splittedline[col]
                        #e.g. 'ConsumedElectricalEnergy_Heating'
                        field = columns[col]
                        field,circuit = field.split("_")

                        logger.debug(f"Spalte: {col} Field: {field} Value: {value}")
                        #logger.debug(f"Field: {field} ")
                        #logger.debug(f"Value: {value}\n")

                        try:
                            #Data Points
                            points.append(influxdb_client.Point(measurement)\
                                .time(utctime, influxdb_client.WritePrecision.S) \
                                .tag("home", home)
                                .tag("device", device)
                                .tag("serial", serial)
                                .tag("circuit", circuit)
                                .field(field, float(value))
                            )
                        except ValueError:
                            print(f"Could not convert value({value}) to float. Skipping this data point.")
                        except Exception as err:
                            print(f"Unexpected {err=}, {type(err)=}")
                        #logger.info(f"LineProto: {points[len(points)-1].to_line_protocol()}\n")

                    #logger.info(f"LineProto: {points[len(points) - 1].to_line_protocol()}\n")

                # Write points to InfluxDB
                logger.info(f"Number of data points: {len(points)}.")

                if writeresults:
                    client = influxdb_client.InfluxDBClient(
                        url=url,
                        token=token,
                        org=org
                    )
                    write_api = client.write_api(write_options=SYNCHRONOUS)
                    try:
                        write_api.write(bucket=bucket, org=org, record=points)
                        logger.info(f"Upload to InfluxDB finished with success.")
                    except Exception as e:
                        #print(f"Failed to upload missed data to InfluxDB: {e}")
                        logger.error(f"Failed to upload missed data to InfluxDB: {e}", exc_info=e)

if __name__ == "__main__":
    args = parser.parse_args()
    kwargs = vars(args)
    verbosity = kwargs.pop("loglevel")
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=verbosity,
        datefmt='%Y-%m-%d %H:%M:%S')
    asyncio.run(main(**kwargs))
