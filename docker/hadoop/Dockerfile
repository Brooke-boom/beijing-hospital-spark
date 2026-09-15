# HDFS（NameNode / DataNode）arm64 原生镜像
# 官方 apache/hadoop 镜像只有 amd64，M1 上需 QEMU 模拟（启动即崩），故自建。
FROM eclipse-temurin:11-jre-jammy

ARG HADOOP_VERSION=3.3.6

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates procps hostname \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    url="https://archive.apache.org/dist/hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}.tar.gz"; \
    curl -fsSL --retry 3 --retry-delay 5 "$url" -o /tmp/hadoop.tar.gz; \
    tar -xzf /tmp/hadoop.tar.gz -C /opt; \
    mv "/opt/hadoop-${HADOOP_VERSION}" /opt/hadoop; \
    rm -f /tmp/hadoop.tar.gz; \
    mkdir -p /data/dfs/name /data/dfs/data /data/tmp

COPY conf/core-site.xml conf/hdfs-site.xml /opt/hadoop/etc/hadoop/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && echo 'export JAVA_HOME=/opt/java/openjdk' >> /opt/hadoop/etc/hadoop/hadoop-env.sh

ENV JAVA_HOME=/opt/java/openjdk \
    HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop \
    PATH=/opt/hadoop/bin:/opt/hadoop/sbin:$PATH

# 9870 NameNode Web UI · 8020 NameNode RPC · 9864 DataNode Web UI
EXPOSE 9870 8020 9864

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
