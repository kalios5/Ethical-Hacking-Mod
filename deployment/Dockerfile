FROM python:latest


RUN apt update \
    && apt install -y gcc libpq-dev
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install gunicorn

COPY app app
#COPY migrations migrations
COPY main.py config.py boot.sh gunicorn.conf.py ./

RUN chmod a+x boot.sh

EXPOSE 5000
ENTRYPOINT ["./boot.sh"]