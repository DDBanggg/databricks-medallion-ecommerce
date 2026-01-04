from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from delta.tables import DeltaTable
from typing import List

class SCD2Handler:
    """
    Class xử lý Slowly Changing Dimension (SCD) Type 2 cho Delta Lake.
    """

    def __init__(self, spark: SparkSession):
        self.spark = spark
        # Định nghĩa tên các cột Audit
        self.col_is_current = "_is_current"
        self.col_effective_date = "_effective_date"
        self.col_end_date = "_end_date"

    def _get_change_condition(self, source_alias: str, target_alias: str, 
                              columns: List[str]) -> F.Column:
        """
        Tạo điều kiện so sánh để phát hiện thay đổi dữ liệu (Change Detection).
        Sử dụng eqNullSafe (<=>) để so sánh đúng cả trường hợp Null.
        """
        condition = F.lit(False)
        for col_name in columns:
            # Logic: Nếu bất kỳ cột nào khác nhau -> Có thay đổi
            # col(a) <=> col(b) trả về True nếu giống nhau (kể cả null)
            # Dấu ~ phủ định lại -> trả về True nếu khác nhau
            condition = condition | (~F.col(f"{source_alias}.{col_name}").eqNullSafe(F.col(f"{target_alias}.{col_name}")))
        return condition

    def upsert_scd_type_2(self, 
                          micro_batch_df: DataFrame, 
                          batch_id: int, 
                          target_table_name: str, 
                          key_columns: List[str], 
                          exclude_columns: List[str] = None):
        """
        Hàm thực thi logic SCD Type 2 Merge.
        Được thiết kế để chạy trong foreachBatch của Spark Structured Streaming.
        """
        
        # 0. Validate input & Clean up
        if micro_batch_df.count() == 0:
            return
        
        if exclude_columns is None:
            exclude_columns = []
            
        # Thêm các cột audit vào danh sách loại trừ để không so sánh
        exclude_columns.extend([self.col_is_current, self.col_effective_date, self.col_end_date])
        
        # Timestamp hiện tại cho batch này (dùng làm effective_date cho row mới và end_date cho row cũ)
        current_ts = F.current_timestamp()

        # Chuẩn bị dữ liệu nguồn (Source) với cột thời gian
        # source_df đại diện cho dữ liệu mới nhất vừa stream về
        source_df = micro_batch_df.withColumn(self.col_effective_date, current_ts) \
                                  .withColumn(self.col_is_current, F.lit(True)) \
                                  .withColumn(self.col_end_date, F.lit(None).cast("timestamp"))

        # ---------------------------------------------------------------------
        # CASE 1: Bảng đích chưa tồn tại (Lần chạy đầu tiên - Initial Load)
        # ---------------------------------------------------------------------
        if not self.spark.catalog.tableExists(target_table_name):
            print(f"Target table {target_table_name} does not exist. Initializing...")
            source_df.write \
                .format("delta") \
                .mode("append") \
                .saveAsTable(target_table_name)
            return

        # ---------------------------------------------------------------------
        # CASE 2: Bảng đích đã có -> Thực hiện MERGE SCD TYPE 2
        # ---------------------------------------------------------------------
        target_table = DeltaTable.forName(self.spark, target_table_name)
        target_df = target_table.toDF()

        # Xác định các cột dữ liệu (Non-key) để so sánh sự thay đổi
        # Lấy tất cả cột trong target trừ key và cột exclude
        all_target_cols = target_df.columns
        value_columns = [c for c in all_target_cols if c not in key_columns and c not in exclude_columns]

        # --- BƯỚC A: Phân loại bản ghi (Identify Changes) ---
        # Join Source với Target (chỉ lấy bản ghi hiện tại is_current=True) để tìm sự khác biệt
        
        # Đổi tên cột target để tránh ambiguous khi join
        target_renamed = target_df.filter(F.col(self.col_is_current) == True) \
                                  .select([F.col(c).alias(f"tgt_{c}") for c in all_target_cols])
        
        join_cond = [F.col(k) == F.col(f"tgt_{k}") for k in key_columns]
        
        joined_df = source_df.join(target_renamed, join_cond, "left")

        # Tạo điều kiện so sánh giá trị
        # Lưu ý: so sánh cột gốc (source) với cột tgt_... (target)
        change_condition = self._get_change_condition("", "tgt", value_columns)

        # Gán nhãn hành động (Action Type)
        # - INSERT: Key không tồn tại bên Target (tgt_key is NULL)
        # - UPDATE: Key tồn tại VÀ có giá trị thay đổi
        # - NO_OP: Key tồn tại nhưng giá trị y hệt (không làm gì)
        staged_df = joined_df.withColumn("action_type", 
            F.when(F.col(f"tgt_{key_columns[0]}").isNull(), "INSERT")
             .when(change_condition, "UPDATE")
             .otherwise("NO_OP")
        ).filter("action_type != 'NO_OP'") # Loại bỏ các bản ghi không đổi để tối ưu

        # --- BƯỚC B: Tạo Merge Source (Union Strategy) ---
        # Để thực hiện SCD2 trong 1 lệnh merge, ta cần:
        # 1. Các dòng cần Insert (Mới hoặc Phiên bản mới của dòng cũ) -> Set mergeKey = NULL
        # 2. Các dòng cần Expire (Phiên bản cũ cần đóng lại) -> Set mergeKey = Actual Key

        # Tập 1: Rows to Insert (Bao gồm cả dòng mới tinh và dòng mới do update)
        rows_to_insert = staged_df.select(source_df.columns) \
                                  .withColumn("mergeKey", F.lit(None)) # Null để ép vào nhánh Not Matched

        # Tập 2: Rows to Expire (Chỉ những dòng Update)
        # Lưu ý: Lúc này ta cần update bảng Target, nên mergeKey phải khớp với Key của Target
        rows_to_update = staged_df.filter("action_type = 'UPDATE'") \
                                  .select(source_df.columns) \
                                  .withColumn("mergeKey", F.concat(*[F.col(k) for k in key_columns])) 
                                  # Nếu nhiều key thì concat lại, hoặc dùng list cột tùy logic merge bên dưới. 
                                  # Đơn giản nhất là dùng 1 cột dummy hoặc giữ nguyên các cột key làm mergeKey.
                                  # Ở đây tôi sẽ dùng cách clean hơn: Giữ nguyên cột key làm mergeKey cho dòng update.
        
        # Cách clean hơn cho mergeKey:
        # Trong rows_to_insert: Set tất cả cột key = NULL (để join fail -> Insert)
        # Trong rows_to_update: Giữ nguyên cột key (để join pass -> Update)
        
        # Refactor lại logic tạo Sets:
        
        # Set 1: Dữ liệu mới cần insert (lấy dữ liệu từ Source)
        # Trick: Ta tạo một cột đặc biệt `__merge_key`
        df_inserts = staged_df.select("*").withColumn("__merge_key", F.lit(None))
        
        # Set 2: Dữ liệu cũ cần update (đóng end_date)
        # Chỉ lấy trường hợp UPDATE. Key join phải là key thực tế.
        df_updates = staged_df.filter("action_type = 'UPDATE'") \
                              .select("*") \
                              .withColumn("__merge_key", F.concat_ws("::", *key_columns)) 

        # Union lại để tạo thành Source cho Merge
        merge_source = df_inserts.unionByName(df_updates)

        # --- BƯỚC C: Thực thi MERGE ---
        # Điều kiện merge: Match key thông qua cột giả `__merge_key`
        # Target Key cũng cần được concat tương ứng để so sánh
        
        merge_condition = F.concat_ws("::", *[F.col(f"target.{k}") for k in key_columns]) == F.col("source.__merge_key")
        # Và chỉ update bản ghi đang active (dù logic trên đã filter, nhưng thêm vào cho chắc chắn)
        merge_condition = merge_condition & (F.col(f"target.{self.col_is_current}") == True)

        target_table.alias("target").merge(
            source=merge_source.alias("source"),
            condition=merge_condition
        ).whenMatchedUpdate(
            # TÌM THẤY (Match): Tức là dòng cũ cần Expire
            set={
                self.col_is_current: F.lit(False),
                self.col_end_date: F.col(f"source.{self.col_effective_date}")
            }
        ).whenNotMatchedInsert(
            # KHÔNG TÌM THẤY (Not Match): Tức là dòng mới cần Insert
            # Vì __merge_key là Null nên nó luôn rơi vào đây
            values={
                **{c: F.col(f"source.{c}") for c in source_df.columns}, # Map tất cả cột nguồn
                self.col_is_current: F.lit(True),
                self.col_effective_date: F.col(f"source.{self.col_effective_date}"),
                self.col_end_date: F.lit(None)
            }
        ).execute()