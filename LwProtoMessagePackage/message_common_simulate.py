#!/usr/bin/env python
# coding=utf8
import time
import re
from proto_tools import *
try:
    # Optional dependency: only needed by simulate_message_quickly_main().
    # When this package is copied under lw_communication/, autotest Keywords may not exist.
    from Keywords.Common.Request.get_orch_info import read_orch_config  # type: ignore
except Exception:  # pragma: no cover
    read_orch_config = None


def create_simulate_messages(log_str, orchId, customerId, clientId):
    """
    替换日志字符串中的指定字段值。

    :param log_str: 原始日志字符串。
    :param new_values: 包含新值的字典，键为字段名称，如 'orchId'。
    :return: 处理过的日志字符串。
    """
    new_values = {
        'orchId': orchId,
        'customerId': customerId,
        'clientId': clientId
    }

    def replace_match(match):
        # 获取要替换的字段名
        field = match.group(1)
        # 如果新值中存在该字段，将其替换为新值，否则保留原值
        return f"{field}={new_values.get(field, match.group(2))}"

    # 匹配模式：捕获字段名称和值
    pattern = r'(\b(?:orchId|customerId|clientId)\b)=(\d+)'

    # 使用 sub 替换所有匹配
    replaced_str = re.sub(pattern, replace_match, log_str)
    return replaced_str


def handle_stats_patch(message):
    lines = message.split("\n")
    lines_list, message_bytes_list, queueName_list = [], [], []
    for i in lines:
        if not i.strip():
            continue
        for j in range(2):
            lines_list.append(i)
            head_dict = handle_header(i)
            message_bytes = message_encode(head_dict)
            message_bytes_list.append(message_bytes)
            queueName = configQueue
            if j ==1:
                queueName = configQueue
            elif head_dict["mtype"] > 600:
                queueName = statsQueue
            # reply 类型：历史上可能用 mtype<200 区分，这里补充支持 402（login reply）等
            elif head_dict["mtype"] < 200 or head_dict["mtype"] == 402 or "reply message" in i:
                queueName = replyQueue
            queueName_list.append(queueName)
    return lines_list, queueName_list, message_bytes_list

def handle_stats_allinone(message):
    lines = message.split("\n")
    lines_list, message_bytes_list, queueName_list = [], [], []
    for i in lines:
        if not i.strip():
            continue
        lines_list.append(i)
        head_dict = handle_header(i)
        message_bytes = message_encode(head_dict)
        message_bytes_list.append(message_bytes)
        queueName = configQueue
        if head_dict["mtype"] > 600:
            queueName = statsQueue
        # reply 类型：历史上可能用 mtype<200 区分，这里补充支持 402（login reply）等
        elif head_dict["mtype"] < 200 or head_dict["mtype"] == 402 or "reply message" in i:
            queueName = replyQueue
        queueName_list.append(queueName)
    return lines_list, queueName_list, message_bytes_list

def handle_stats_allinone(message):
    lines = message.split("\n")
    lines_list, message_bytes_list, queueName_list = [], [], []
    for i in lines:
        if not i.strip():
            continue
        lines_list.append(i)
        head_dict = handle_header(i)
        message_bytes = message_encode(head_dict)
        message_bytes_list.append(message_bytes)
        queueName = configQueue
        if head_dict["mtype"] > 600:
            queueName = statsQueue
        # reply 类型：历史上可能用 mtype<200 区分，这里补充支持 402（login reply）等
        elif head_dict["mtype"] < 200 or head_dict["mtype"] == 402 or "reply message" in i:
            queueName = replyQueue
        queueName_list.append(queueName)
    return lines_list, queueName_list, message_bytes_list

def send_stats(redis_info, repeat, speed_info, group_interval, total_group, lines_list, queue_list,
               message_bytes_list,
               line_num):
    config_count, stats_count, reply_count = 0, 0, 0
    current_thread_name = threading.current_thread().name
    cpeid_pattern = re.compile(r"clientId=(\d+)")
    for group in range(int(total_group)):
        num = line_num
        for j in range(int(repeat)):
            for index, line in enumerate(lines_list):
                if "timestamp:" in line:
                    init_timestamp = int(line.split("timestamp: ")[1].split(" ")[0])
                    print(f"原时间戳为：{init_timestamp}")
                    current_timestamp = int(round(time.time(), 6) * 1000000)
                    line = line.replace(rf"timestamp: {init_timestamp}", rf"timestamp: {current_timestamp}")
                    current_timestamp = int(line.split("timestamp: ")[1].split(" ")[0])
                    print(f"当前时间戳为：{current_timestamp}")
                match = cpeid_pattern.search(line)
                cpeId = match.group(1)
                print(
                    f"线程[{current_thread_name}]：第{num}行(原文件行数索引)的消息正在发送，请等待。。。。。。 clientId={cpeId}")
                num += 1
                head_dict = handle_header(line)
                message_bytes_list[index] = message_encode(head_dict)

                redis_info.lpush(queue_list[index], message_bytes_list[index])
                if queue_list[index] == configQueue:
                    config_count += 1
                elif queue_list[index] == statsQueue:
                    stats_count += 1
                elif queue_list[index] == replyQueue:
                    reply_count += 1
                if speed_info != "0" or j != int(repeat) - 1:
                    time.sleep(float(speed_info))
        if group_interval != "0" or group != int(total_group) - 1:
            time.sleep(float(group_interval))
    print("info",
          rf"消息发送完成，本次ServerToOrchCfg队列共发送消息{config_count}条，ServerToOrchSta队列共发送消息{stats_count}条，ServerToOrchReply队列共发送消息{reply_count}条")


def simulate_message_quickly_main(orch_env, messages, repeated=1, speed=0, threads=1, group_message_intervals=1,
                                  total_group_message=1):
    if read_orch_config is None:
        raise RuntimeError(
            "read_orch_config import failed. If you want to use simulate_message_quickly_main(), "
            "please run from the autotest environment or provide redis_info directly via "
            "simulate_message_quickly_jenkins()."
        )
    orch_info = read_orch_config(orch_env)
    redis_info = {"ip": orch_info['proto_redis']['ip'], "port": orch_info['proto_redis']['port'],
                  "password": orch_info['proto_redis']['password'], "db": orch_info['proto_redis']['db']}
    if orch_env =='autotest_zone2':
        redis_master = get_master_address(redis_info, 'mymaster')
        print(redis_master)
        redis_info = eval(str(redis_master))
    print(redis_info)
    redis_cli = redis_connect(redis_info)
    # 根据部署方式选择不同的处理函数
    if 'how_to_deploy' in orch_info and orch_info['how_to_deploy'] == 'all-in-one':
        lines, queueName_list, message_bytes_list = handle_stats_allinone(messages)
    else:
        lines, queueName_list, message_bytes_list = handle_stats_patch(messages)

    start_line_nums = []
    lines_per_thread = len(lines) // int(threads)
    extra_lines = len(lines) % int(threads)
    start_index = 0
    redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list, queue_list_list, message_bytes_list_list = [], [], [], [], [], [], [], []
    for i in range(int(threads)):
        end_index = start_index + lines_per_thread + (1 if i < extra_lines else 0)
        sub_lines = lines[start_index:end_index]
        sub_queue_list = queueName_list[start_index:end_index]
        sub_message_bytes = message_bytes_list[start_index:end_index]
        start_line_num = start_index + 1
        start_line_nums.append(start_line_num)
        start_index = end_index
        redis_cli_list.append(redis_cli)
        repeated_list.append(repeated)
        speed_list.append(speed)
        group_interval_list.append(group_message_intervals)
        group_total_list.append(total_group_message)
        lines_list_list.append(sub_lines)
        queue_list_list.append(sub_queue_list)
        message_bytes_list_list.append(sub_message_bytes)
    argvs_list = [redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list,
                  queue_list_list, message_bytes_list_list, start_line_nums]
    my_thread_multi_argvs(send_stats, argvs_list)


def simulate_message_quickly_jenkins(repeated, speed, redis_info, messages, threads, group_message_intervals, total_group_message,orch_deploy):
    redis_info = eval(str(redis_info))
    redis_cli = redis_connect(redis_info)
    if 'allInOne' in orch_deploy:
        lines, queueName_list, message_bytes_list = handle_stats_allinone(messages)
    else:
        lines, queueName_list, message_bytes_list = handle_stats_patch(messages)
    start_line_nums = []
    lines_per_thread = len(lines) // int(threads)
    extra_lines = len(lines) % int(threads)
    start_index = 0
    redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list, queue_list_list, message_bytes_list_list = [], [], [], [], [], [], [], []
    for i in range(int(threads)):
        end_index = start_index + lines_per_thread + (1 if i < extra_lines else 0)
        sub_lines = lines[start_index:end_index]
        sub_queue_list = queueName_list[start_index:end_index]
        sub_message_bytes = message_bytes_list[start_index:end_index]
        start_line_num = start_index + 1
        start_line_nums.append(start_line_num)
        start_index = end_index
        redis_cli_list.append(redis_cli)
        repeated_list.append(repeated)
        speed_list.append(speed)
        group_interval_list.append(group_message_intervals)
        group_total_list.append(total_group_message)
        lines_list_list.append(sub_lines)
        queue_list_list.append(sub_queue_list)
        message_bytes_list_list.append(sub_message_bytes)
    argvs_list = [redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list,
                  queue_list_list, message_bytes_list_list, start_line_nums]
    my_thread_multi_argvs(send_stats, argvs_list)


def simulate_message_quickly_jenkins_bak(repeated, speed, redis_info, messages, threads, group_message_intervals, total_group_message):
    redis_info = eval(str(redis_info))
    redis_cli = redis_connect(redis_info)
    # historical fallback: use patch-style routing
    lines, queueName_list, message_bytes_list = handle_stats_patch(messages)
    redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list, queue_list_list, message_bytes_list_list = [], [], [], [], [], [], [], []
    for i in range(int(threads)):
        redis_cli_list.append(redis_cli)
        repeated_list.append(repeated)
        speed_list.append(speed)
        group_interval_list.append(group_message_intervals)
        group_total_list.append(total_group_message)
        lines_list_list.append(lines)
        queue_list_list.append(queueName_list)
        message_bytes_list_list.append(message_bytes_list)
    argvs_list = [redis_cli_list, repeated_list, speed_list, group_interval_list, group_total_list, lines_list_list, queue_list_list, message_bytes_list_list]
    my_thread_multi_argvs(send_stats, argvs_list)

if __name__ == "__main__":
    # msg = LwProtoMsgSimulate()
    messages_tmp = '''2024-10-28 14:06:47.966 [recv-stat-0] DEBUG cloudwan.cpe.proto.message.StatsMessageReceiver [] - recv stat message: version=48 reserved=0 orchId=19096 customerId=1909622898 clientId=1 tranId=365869 type=635 payload=netId: 0 transactionId: 365869 msgBase { statsReportV2 { timestamp: 1730095607949439 systemStats { cpuUsage: 100 cpuUsage: 100 cpuUsage: 100 memTotal: 100 memUsed: 1 diskTotal: 100 diskUsed: 1 commSrvTcpBufData { recvBufSize: 0 sendBufSize: 0 } } } statsReportV2 { vpnId: 0 timestamp: 1730095607949439 wanStats { wanInterface { interfaceName: "eth1" interfaceType: 2 rxBytes: 3230900662 txBytes: 7146838404 rxPackets: 41292911 txPackets: 66151995 rxBps: 949 txBps: 2105 rxPps: 12 txPps: 19 smoothrxBps: 951 smoothtxBps: 2102 smoothrxPps: 8 smoothtxPps: 16 incRxBytes: 9492 incTxBytes: 21054 incRxPkts: 122 incTxPkts: 195 } wanID: 1 isWanUp: true  } totalActiveFlows: 0 lanStat { lanStats { interfaceName: "eth0" interfaceType: 1 rxBytes: 0 txBytes: 0 rxPackets: 0 txPackets: 0 rxBps: 0 txBps: 0 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } lanId: 1 isLanUp: true }} } fragInfo { fragSeq: 0 endFlag: true }'''
    messages_tmp ='''2024-12-13 15:23:02.015 [recv-stat-0] DEBUG cloudwan.cpe.proto.message.StatsMessageReceiver [] - recv stat message: version=48 reserved=0 orchId=19889 customerId=1988914621 clientId=28 tranId=818911 type=635 payload=netId: 0 transactionId: 818911 msgBase { statsReportV2 { timestamp: 1734074581998289 systemStats { cpuUsage: 188 cpuUsage: 93 cpuUsage: 140 memTotal: 1839 memUsed: 1033 diskTotal: 13706 diskUsed: 1952 commSrvTcpBufData { recvBufSize: 0 sendBufSize: 0 } } linkStats { linkID: 10776 linkType: 1 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 834275988 rxBytes: 0 txPackets: 8056688 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "30.30.30.2" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10772 linkType: 1 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 843881778 rxBytes: 0 txPackets: 8083823 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "10.10.10.2" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10765 linkType: 1 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 837202860 rxBytes: 0 txPackets: 8064956 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "1.1.1.2" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10737 linkType: 2 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 570245442 rxBytes: 0 txPackets: 7310839 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "10.30.68.13" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10736 linkType: 2 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 570245442 rxBytes: 0 txPackets: 7310839 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "2.2.2.2" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10735 linkType: 2 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 570245442 rxBytes: 0 txPackets: 7310839 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "1.1.1.2" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } linkStats { linkID: 10734 linkType: 2 rtt: 0 pktLoss: 0 peerPktLoss: 0 jitter: 0 txBytes: 570245442 rxBytes: 0 txPackets: 7310839 rxPackets: 0 rxBps: 0 txBps: 78 rxPps: 0 txPps: 1 smoothrxBps: 0 smoothtxBps: 66 smoothrxPps: 0 smoothtxPps: 1 srcIP: "10.30.62.149" dstIP: "192.168.7.9" realtimeRtt: 0 realtimePktLoss: 0 realtimePeerPktLoss: 0 realtimeJitter: 0 incRxBytes: 0 incTxBytes: 780 incRxPkts: 0 incTxPkts: 10 } } statsReportV2 { vpnId: 0 timestamp: 1734074581998289 wanStats { wanInterface { interfaceName: "eth1" interfaceType: 2 rxBytes: 5791767960 txBytes: 14855336454 rxPackets: 74005323 txPackets: 129325077 rxBps: 487 txBps: 1638 rxPps: 6 txPps: 13 smoothrxBps: 493 smoothtxBps: 1655 smoothrxPps: 2 smoothtxPps: 8 incRxBytes: 4878 incTxBytes: 16382 incRxPkts: 63 incTxPkts: 135 } wanID: 1 isWanUp: true wanPriorityStats { wanPriority: 0 rxBytes: 5791600302 txBytes: 14855329874 rxBps: 487 txBps: 1638 rxPackets: 74003050 txPackets: 129325007 rxPps: 6 txPps: 13 smoothrxBps: 493 smoothtxBps: 1655 smoothrxPps: 2 smoothtxPps: 8 incRxBytes: 4878 incTxBytes: 16382 incRxPkts: 63 incTxPkts: 135 } wanPriorityStats { wanPriority: 1 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 2 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 3 rxBytes: 2352 txBytes: 1316 rxBps: 0 txBps: 0 rxPackets: 28 txPackets: 14 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 4 rxBytes: 2352 txBytes: 1316 rxBps: 0 txBps: 0 rxPackets: 28 txPackets: 14 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 5 rxBytes: 2352 txBytes: 1316 rxBps: 0 txBps: 0 rxPackets: 28 txPackets: 14 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 6 rxBytes: 2352 txBytes: 1316 rxBps: 100 txBps: 100 rxPackets: 28 txPackets: 14 rxPps: 100 txPps: 100 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } wanPriorityStats { wanPriority: 7 rxBytes: 2352 txBytes: 1316 rxBps: 0 txBps: 0 rxPackets: 28 txPackets: 14 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } } policyStats { policyId: 353 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 354 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 355 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 356 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 357 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 358 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2147483649 rxBytes: 178670564 txBytes: 4130717596 rxBps: 15 txBps: 617 rxPackets: 2568038 txPackets: 3907321 rxPps: 0 txPps: 0 activeFlows: 1 smoothrxBps: 16 smoothtxBps: 621 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 156 incTxBytes: 6172 incRxPkts: 3 incTxPkts: 5 } policyStats { policyId: 410 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 396 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 399 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 400 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 402 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 407 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 412 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 443 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2156483649 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2156483650 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2156483648 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2154483649 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2155487746 rxBytes: 0 txBytes: 0 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 0 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 359 rxBytes: 13487774 txBytes: 281597288 rxBps: 0 txBps: 0 rxPackets: 206276 txPackets: 291775 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } totalActiveFlows: 1 lanStat { lanStats { interfaceName: "eth0" interfaceType: 1 rxBytes: 0 txBytes: 0 rxPackets: 0 txPackets: 0 rxBps: 0 txBps: 0 rxPps: 0 txPps: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } lanId: 1 isLanUp: false } lanOnlineIpNum: 0 } statsReportV2 { vpnId: 4294967295 timestamp: 1734074581998289 policyStats { policyId: 2147483668 rxBytes: 47526 txBytes: 885120 rxBps: 0 txBps: 0 rxPackets: 555 txPackets: 766 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } policyStats { policyId: 2147483678 rxBytes: 0 txBytes: 90412 rxBps: 0 txBps: 0 rxPackets: 0 txPackets: 1737 rxPps: 0 txPps: 0 activeFlows: 0 smoothrxBps: 0 smoothtxBps: 0 smoothrxPps: 0 smoothtxPps: 0 exclusiveMode: false incRxBytes: 0 incTxBytes: 0 incRxPkts: 0 incTxPkts: 0 } totalActiveFlows: 0 } } fragInfo { fragSeq: 0 endFlag: true }'''
    # redis_info = {"ip": "10.4.252.33", "port": "6380", "password": "appexnetworks243", "db": "0"}
    # messages = create_simulate_messages(messages_tmp, 19096, 1909622804, 2)
    message = 'D:/zh_cpe_635_message_mulCpe_01.txt'
    with open(message,"r") as f:
        messages_tmp = f.read()
    simulate_message_quickly_jenkins(1,0, {"ip":"10.30.68.2","port":"6380","password":"appexnetworks243","db":"0"}, messages_tmp, 20, 10, 100)
