FROM spark@sha256:d9c96395b753a3403e77b90f7b37a2ac24078cb2ae38fdc0bbcfc56cc1a35751

LABEL org.opencontainers.image.source=https://github.com/rhprasad0/chaos-lab
USER root
ARG JDBC_VERSION=42.7.14
ARG JDBC_SHA256=73914527305a40cce504b0d3d90b23caf565136912d607ae8ae7c5895512332c
RUN curl -fsSLo /opt/spark/jars/postgresql.jar \
      "https://repo1.maven.org/maven2/org/postgresql/postgresql/${JDBC_VERSION}/postgresql-${JDBC_VERSION}.jar" \
 && echo "${JDBC_SHA256}  /opt/spark/jars/postgresql.jar" | sha256sum -c - \
 && pip3 install --no-cache-dir pytest==8.4.2 \
 && mkdir -p /lake /seed && chown spark:spark /lake /seed
USER spark
ENV PATH="/opt/spark/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.9-src.zip"
