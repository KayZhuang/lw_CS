## LwProtoMessagePackage（Proto Redis 消息注入工具）

这份目录从 `autotest/Tools/LwProtoMessagePackage/` 复制到 `lw_communication/tools/`，用于**往 Proto Redis（事件队列）写入模拟消息**（`LPUSH`）。

### 关键文件
- `message_common_simulate_main.py`：命令行入口（jenkins 风格参数）
- `message_common_simulate.py`：核心逻辑（多线程、分组间隔、重复发送）
- `proto_tools.py`：Redis 连接、header/payload 编码、队列名常量

### 队列名（见 `proto_tools.py`）
- `ServerToOrchCfg`
- `ServerToOrchSta`
- `ServerToOrchReply`

### 依赖
需要 Python 包：
- `redis`
- `protobuf`
- `numpy`

（如缺失请自行 `pip install redis protobuf numpy`）

### 使用方式（直接指定 redis_info）

在该目录下运行：

```bash
cd /path/to/lightwan/lw_communication/tools/LwProtoMessagePackage

# 参数说明：
# 1 repeated：每条消息重复次数
# 2 speed：每条消息间隔（秒）
# 3 redis_info：形如 "{'ip':'x.x.x.x','port':'6380','password':'xxx','db':'0'}"
# 4 message_file：包含消息模板的文件路径（文本日志形式，含 version/orchId/customerId/clientId/tranId/type/payload=...）
# 5 threads：线程数
# 6 group_message_intervals：组间间隔（秒）
# 7 total_group_message：组数
# 8 requirement：correctly/quickly（当前脚本主要用 quickly 路径）
# 9 orch_deploy：包含 allInOne 时走 all-in-one 处理，否则走 patch 处理

python3 message_common_simulate_main.py \
  1 \
  0 \
  "{'ip':'10.30.68.2','port':'6380','password':'appexnetworks243','db':'0'}" \
  ./your_messages.txt \
  20 \
  10 \
  100 \
  quickly \
  allInOne
```

### 说明
- 本工具**只负责写入 Proto Redis 队列**，要产生“真实业务回包/状态变化”，仍需要对应的消费端服务（如 RCS/worker/broker consumer）在消费这些队列。

