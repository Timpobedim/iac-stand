# Jenkins и он же «ящик инструментов» стенда: Terraform, Ansible, docker CLI, pytest.
# Одни и те же версии в пайплайне и на машине разработчика: docker compose run --rm tools …
FROM jenkins/jenkins:2.568.3-lts-jdk21

USER root
ARG TERRAFORM_VERSION=1.16.3
ARG TERRAFORM_SHA256=093b6ae9a2228af5029c41606bc96eb583553528aad1bfe7e0b4d62fc91e25d8
ARG DOCKER_CLI_VERSION=29.8.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv curl unzip make git \
    && rm -rf /var/lib/apt/lists/*

# Terraform — с проверкой контрольной суммы из SHA256SUMS HashiCorp.
RUN curl -fsSL -o /tmp/tf.zip \
        "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && echo "${TERRAFORM_SHA256}  /tmp/tf.zip" | sha256sum -c - \
    && unzip -q /tmp/tf.zip -d /usr/local/bin terraform && rm /tmp/tf.zip

# Только клиент docker: демон — на хосте, доступ через проброшенный сокет.
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
    | tar -xz --strip-components=1 -C /usr/local/bin docker/docker

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/tools \
    && /opt/tools/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && /opt/tools/bin/ansible-galaxy collection install community.docker:5.3.0 -p /usr/share/ansible/collections
ENV PATH=/opt/tools/bin:$PATH

# Репозиторий монтируется с хоста от другого владельца — git иначе откажется с ним работать.
RUN git config --system --add safe.directory '*'

COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt --list | tail -n 40

COPY casc.yaml /usr/share/jenkins/ref/casc.yaml
ENV CASC_JENKINS_CONFIG=/usr/share/jenkins/ref/casc.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true"

USER jenkins
