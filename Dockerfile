FROM python:3.13-alpine

WORKDIR /app

# Python Stuff
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

#COPY application
COPY vaillant2influx.py /app/vaillant2influx.py

# Prepare and run crontab
COPY crontab /etc/cron.d/crontab
RUN chmod 0644 /etc/cron.d/crontab
RUN /usr/bin/crontab /etc/cron.d/crontab

# run crond as main process of container
CMD ["crond", "-f"]
#CMD ["/app/vaillant2influx.py", "-c", "germany", "-y", "2024", "-a", "skopetzki@web.de", "-p", "Pezov.Axuje101", "-b", "vaillant", "-o", "kopetzki", "-t", "JCgWvmy5pfaLnonepxFw6KBesEDezo8LkbgJKc03b0xF4xV_vxu5REsZNSMz70J4iyeiipur5giht2nSN8XjnA==", "-u", "http://192.168.0.144:8086", "-m", "Flexotherm"]
#CMD ["/app/vaillant2influx.py"]