FROM python:3.8

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED 1

ARG USERNAME=vscode
ARG USERID=1000
ARG GROUPID=1000

RUN set -e -x ; \
    ln -sf /usr/share/zoneinfo/Europe/Lisbon /etc/localtime ; \
    apt-get update ; \
    apt-get install --yes \
        sudo \
        apt-utils dialog git openssh-client iproute2 procps lsb-release ; \
    apt-get autoremove --yes ; \
    apt-get clean --yes ; \
    rm -rf /var/lib/apt/lists/*;

WORKDIR /code
COPY salt-service/requirements.txt .

RUN set -e -x ; \
    pip3 install -U pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    rm -rf /tmp/pip-build-root

RUN set -e -x ; \
    grep -q ":$GROUPID:" /etc/group || groupadd --gid $GROUPID $USERNAME ; \
    useradd --shell /bin/bash --uid $USERID --gid $GROUPID -m $USERNAME ; \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME; \
    chmod 0440 /etc/sudoers.d/$USERNAME

USER $USERNAME

COPY salt-service/.env .env
COPY salt-service/salt_generator.py salt_generator.py

CMD [ "python3", "salt_generator.py" ]