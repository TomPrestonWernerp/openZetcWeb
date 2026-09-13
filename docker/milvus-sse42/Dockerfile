FROM milvusdb/milvus:v2.5.6
COPY libopenzetc-cpu-compat.so /milvus/lib/libopenzetc-cpu-compat.so
COPY user.yaml /milvus/configs/user.yaml
ENV LD_PRELOAD=/milvus/lib/libopenzetc-cpu-compat.so
