#!/usr/bin/env python
# coding=utf8
import sys
from message_common_simulate import simulate_message_quickly_jenkins

def simulate_main(repeated, speed, redis_info, messages, threads, group_message_intervals, total_group_message, requirement,orch_deploy):
    simulate_message_quickly_jenkins(repeated, speed, redis_info, messages, threads,
                                                                      group_message_intervals, total_group_message,orch_deploy)


def simulate_and_check_main():
    pass


if __name__ == '__main__':
    repeated = sys.argv[1]  # 每条消息重复发送次数
    speed = sys.argv[2]  # 每条消息发送的间隔时间，单位秒
    redis_info = sys.argv[3]  # redis连接信息
    message = sys.argv[4]  # 消息发送的模板
    with open(message,"r") as f:
        messages = f.read()
    threads = sys.argv[5]  # 多线程的个数
    group_message_intervals = sys.argv[6]  # 第一组和第二组的时间间隔
    total_group_message = sys.argv[7]  # 总的消息组数
    requirement = sys.argv[8]  # 要求：填correctly或者quickly
    orch_deploy = sys.argv[9]
    simulate_main(repeated, speed, redis_info, messages, threads, group_message_intervals, total_group_message, requirement,orch_deploy)



