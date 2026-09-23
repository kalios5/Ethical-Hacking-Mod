FROM python:latest


RUN apt update  && \
    apt install -y --no-install-recommends cron && \
    apt install -y gcc libpq-dev postgresql-client
COPY deployment/requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

COPY app app
COPY migrations migrations
COPY main.py app/config.py deployment/boot.sh ./
RUN chmod a+x boot.sh

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]