from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, col
from pyspark.sql.streaming import StreamingQuery
import os

def load_raw_to_bronze(
    spark: SparkSession,
    source_path: str,
    table_name: str,
    checkpoint_path: str,
    schema_hints: str = None,
    path_glob_filter: str = None
) -> StreamingQuery:
    """
    Ingest dữ liệu CSV Raw vào bảng Bronze Delta sử dụng Auto Loader.
    """
    
    schema_location = os.path.join(checkpoint_path, "_schema")

    # 1. Cấu hình Reader
    reader = spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "csv") \
        .option("header", "true") \
        .option("delimiter", ",") \
        .option("cloudFiles.inferColumnTypes", "true") \
        .option("cloudFiles.schemaLocation", schema_location)
    
    if path_glob_filter:
        reader = reader.option("pathGlobFilter", path_glob_filter)
    
    if schema_hints:
        reader = reader.option("cloudFiles.schemaHints", schema_hints)
        
    df_raw = reader.load(source_path)

    # 2. Transformation
    df_transformed = df_raw.withColumn("_source_file", col("_metadata.file_path")) \
                           .withColumn("_ingested_at", current_timestamp())

    # 3. Write Stream
    query = df_transformed.writeStream \
        .format("delta") \
        .outputMode("append") \
        .option("checkpointLocation", checkpoint_path) \
        .option("mergeSchema", "true") \
        .trigger(availableNow=True) \
        .table(table_name)
    
    return query