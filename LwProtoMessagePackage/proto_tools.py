#!/usr/bin/env python
# coding=utf8
from LwProto import LightwanMsg_pb2
from google.protobuf.text_format import Parse
from struct import *
from ctypes import *
import numpy as np
import redis
import threading

configQueue = "ServerToOrchCfg"  # 配置类，代表rcs
statsQueue = "ServerToOrchSta"  # 统计类，代表mars
smStatsQueue = "ServerToOrchSta_SM"  # 代表商密统计类消息
smConfigQueue = "ServerToOrchCfg_SM"  # 代表商密配置类消息
replyQueue = "ServerToOrchReply"
# header总长度为20 bytes
plainHeaderLen = 20
# 签名sign的字节长度
paraLen = 64


def handle_header(line, msg_type="normal"):
    version = line.split("version=")[1].split(" ")[0]
    orchId = line.split("orchId=")[1].split(" ")[0]
    customerId = line.split("customerId=")[1].split(" ")[0]
    clientId = line.split("clientId=")[1].split(" ")[0]
    mtype = line.split("type=")[1].split(" ")[0]
    payload_text = line.split("payload=")[1]
    tranId = line.split("tranId=")[1].split(" ")[0]
    # 将一个文本payload解析成protobuf格式的payload
    payload_proto = Parse(payload_text, LightwanMsg_pb2.PayloadType())
    # 将protobuf对象序列化成字节数组
    payload_bytes = payload_proto.SerializeToString()

    plen = len(payload_bytes)
    if msg_type == "sm":
        plen = len(payload_bytes) + paraLen

    # message header字典
    header_dict = {
        "version": int(version),
        "orchId": int(orchId),
        "customerId": int(customerId),
        "clientId": int(clientId),
        "mtype": int(mtype),
        "plen": int(plen),
        "tranId": int(tranId),
        "payload": payload_bytes
    }
    return header_dict


def message_encode(plain_header_dict):
    # H代表unsigned short ==>2 bytes  I代表unsigned int ==>4 bytes  s代表string ==> 1 byte   >代表大端
    fmt = Struct(f'>HHIHHII{plain_header_dict["plen"]}s')
    buffer = create_string_buffer(plainHeaderLen + plain_header_dict["plen"])
    Struct.pack_into(fmt, buffer, 0, plain_header_dict["version"], plain_header_dict["orchId"],
                     plain_header_dict["customerId"], plain_header_dict["clientId"], plain_header_dict["mtype"],
                     plain_header_dict["plen"], plain_header_dict["tranId"], plain_header_dict["payload"])
    # 以下两行等于buffer.raw
    data = np.frombuffer(buffer, dtype=np.uint8)
    data = bytes(data)
    return data


def redis_connect(redis_ssh):
    redis_pool = redis.ConnectionPool(host=redis_ssh["ip"], port=redis_ssh["port"], password=redis_ssh["password"],
                                      db=redis_ssh["db"])
    redis_conn = redis.StrictRedis(connection_pool=redis_pool)
    return redis_conn


def str_replace(message, old, diff):
    result = int(message.split(old)[1].split(" ")[0])
    result = result + diff
    result = str(result)
    return result


def my_thread_multi_argvs(target, argv_list):
    threads = []
    new_argv_list = []
    # 二维列表 行列转换
    for i in range(len(argv_list[0])):
        inner_list = []
        for j in range(len(argv_list)):
            inner_list.append(argv_list[j][i])
        new_argv_list.append(inner_list)
    # 多线程处理
    for i in new_argv_list:
        t = threading.Thread(target=target, args=tuple(i))
        threads.append(t)
        t.start()
    [thread.join() for thread in threads]


def get_master_address(redis_info, master_name):
    """
    获取指定主节点的地址信息。
    """
    sentinel_hosts = [(redis_info['ip'], 26399)]
    # 创建 Redis Sentinel 实例
    sentinel = redis.sentinel.Sentinel(sentinel_hosts)
    print(sentinel)

    try:
        # 使用 get_master_address_by_name 查询主节点信息
        master = sentinel.discover_master(master_name)
        if master[0] != redis_info['ip']:
            redis_info['ip'] = master[0]
        return redis_info

    except Exception as e:
        print(f"Error fetching master address: {e}")


