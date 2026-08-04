# Reference execution image recipe for the python-src-py312-v1 profile.
#
# The build context must contain `fixture/` (the frozen reference fixture
# tree, byte-for-byte) and `requirements.lock` (byte-identical to
# requirements/reference.lock).  T02.1's image builder assembles exactly this
# context from the frozen repository state and builds with the fixed
# builder/output/media-type/compression/attestation parameters recorded in
# spikes/docker_reference_boundary/image_builder.py.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY fixture/ /app/
COPY requirements.lock /app/requirements.lock

RUN pip install --no-cache-dir --no-deps --require-hashes -r /app/requirements.lock \
    && useradd --system --uid 10001 --shell /usr/sbin/nologin --no-create-home vesper

USER vesper

CMD ["python"]
