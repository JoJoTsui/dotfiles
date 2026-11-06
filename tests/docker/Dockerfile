ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG UBUNTU_RELEASE
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git bzip2 xz-utils unzip procps util-linux iproute2 ruby \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /bin/bash verifier

COPY --chown=10001:10001 . /source
ENV HOME=/home/verifier LANG=C.UTF-8 TERM=xterm-256color \
    DOTFILES_TEST_UBUNTU_RELEASE=${UBUNTU_RELEASE} PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 RAYON_NUM_THREADS=3 \
    MAKEFLAGS=-j3 NODE_OPTIONS=--max-old-space-size=2048
USER verifier
WORKDIR /source
ENTRYPOINT ["/bin/bash", "/source/tests/docker/entrypoint.sh"]
