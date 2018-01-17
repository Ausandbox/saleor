FROM python:3.5
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y wget openssh-client

ADD requirements.txt /app/

# add the authorized host key for github (avoids "Host key verification failed")
RUN mkdir ~/.ssh && ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts


ARG host

ENV PRIVATE_KEY /root/.ssh/id_rsa

RUN wget -O $PRIVATE_KEY http://$host:8080/v1/secrets/file/id_rsa \
&& chmod 0600 $PRIVATE_KEY \
&& pip install -r app/requirements.txt \
&& rm $PRIVATE_KEY

RUN pip install gunicorn

ADD . /app

EXPOSE 8000

RUN mkdir /srv/logs/

WORKDIR /app

ENTRYPOINT ["/docker-entrypoint.sh"]
