import threading
import os
import traceback
import pika
import setting
import time
from tools.built_in.log import log
from tools.toolslib import ExceptErrorThread
import requests
import json
logger = log(__name__)


class Heartbeat(threading.Thread):
    """
    在同步消息消费的时候可能会出现pika库断开的情况，原因是因为pika客户端没有及时发送心跳，连接就被server端断开了。
    解决方案就是做一个心跳线程来维护连接。
    """
    def __init__(self, connection):
        super(Heartbeat, self).__init__()
        self.lock = threading.Lock()  # 线程锁
        self.connection = connection  # rabbit连接
        self.quitflag = False  # 退出标志
        self.stopflag = True  # 暂停标志
        self.setDaemon(True)  # 设置为守护线程，当消息处理完，自动清除

    # 间隔10s发送心跳
    def run(self):
        while not self.quitflag:
            time.sleep(10)  # 睡10s发一次心跳
            self.lock.acquire()  # 加线程锁
            if self.stopflag:
                self.lock.release()
                continue
            try:
                self.connection.process_data_events()  # 一直等待服务段发来的消息
            except Exception as e:
                print("Error format: %s" % (str(e)))
                self.lock.release()
                return
            self.lock.release()

    # 开启心跳保护
    def startheartbeat(self):
        # logger.debug("心态线程开始！")
        self.lock.acquire()
        if self.quitflag:
            self.lock.release()
            return
        self.stopflag = False
        self.lock.release()


class RabbitMq:
    def __init__(self, name, connection, channel, rabbitmq_host, rabbitmq_user, rabbitmq_pwd):
        self.name = name
        self.connection = connection
        self.channel = channel
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_user = rabbitmq_user
        self.rabbitmq_pwd = rabbitmq_pwd

    @classmethod
    def connect(cls, name, rabbitmq_host, rabbitmq_user, rabbitmq_pwd, ):
        logger.debug("开始连接rabbitmq队列！")

        user_pwd = pika.PlainCredentials(rabbitmq_user, rabbitmq_pwd)

        parameters = (
            pika.ConnectionParameters(host=rabbitmq_host, credentials=user_pwd, heartbeat=0),
            pika.ConnectionParameters(host=rabbitmq_host, credentials=user_pwd, heartbeat=0,
                                      connection_attempts=5, retry_delay=1))
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=name, durable=True, arguments=False)
        return cls(name, connection, channel, rabbitmq_host, rabbitmq_user, rabbitmq_pwd)

    def queue_declare(self, name=None, durable=True, args=False):
        if not name:
            name = self.name
        queue = self.channel.queue_declare(queue=name, durable=durable, arguments=args)
        return queue

    def pulish(self, body, priority=0):
        self.channel.basic_publish(
            exchange='',
            routing_key=self.name,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                priority=priority
            ))

    def del_queue(self, name=None, if_unused=False, if_empty=False):
        if not name:
            name = self.name
        self.queue_declare(name)
        self.channel.queue_delete(
            queue=name,
            if_unused=if_unused,
            if_empty=if_empty
        )

    def purge(self, name=None):
        if not name:
            name = self.name
        self.queue_declare(name)
        self.channel.queue_purge(name)

    def is_empty(self, name=None, rabbitmq_host="127.0.0.1", rabbitmq_user=None, rabbitmq_pwd=None, port=15672):
        if not name:
            name = self.name
        res = requests.get(
            url='http://{}:{}/api/queues/{}/{}'.format(rabbitmq_host, "15672", "%2F", name),
            auth=(rabbitmq_user, rabbitmq_pwd)
        )
        res = json.loads(res.content.decode())
        return int(res["messages"])

    def consume(self, name=None, callback=None, prefetch_count=1, channel=None, connection=None):
        if not channel:
            channel = self.channel
        if not connection:
            connection = self.connection
        if not name:
            name = self.name
        self.queue_declare(name)
        channel.basic_qos(prefetch_count=prefetch_count)
        channel.basic_consume(
            queue=name,
            on_message_callback=callback,
            auto_ack=False
        )
        heartbeat = Heartbeat(connection)  # 实例化一个心跳类
        heartbeat.start()  # 开启一个心跳线程，不传target的值默认运行run函数
        heartbeat.startheartbeat()  # 开启心跳保护
        try:
            consu = ExceptErrorThread(self.channel.start_consuming)
            consu.setDaemon(True)
            consu.start()
            while True:
                consu.join(60)
                if self.is_empty(
                        name=name,
                        rabbitmq_host=self.rabbitmq_host,
                        rabbitmq_user=self.rabbitmq_user,
                        rabbitmq_pwd=self.rabbitmq_pwd,
                ) == 0:
                    self.del_queue(self.name)
                    break
        except Exception as e:
            logger.error(e)
            print(e)


def connecting(name, rabbitmq_host, rabbitmq_user, rabbitmq_pwd):
    if name:
        if rabbitmq_host:
            setting.rabbitmq_host = rabbitmq_host
        elif setting.rabbitmq_host:
            rabbitmq_host = setting.rabbitmq_host
        else:
            setting.rabbitmq_host = rabbitmq_host = "127.0.0.1"

        if rabbitmq_user:
            setting.rabbitmq_user = rabbitmq_user
        elif setting.rabbitmq_user:
            rabbitmq_user = setting.rabbitmq_user
        else:
            logger.error("未配置RabbitMq用户名")
            raise ValueError("未配置RabbitMq用户名")

        if rabbitmq_pwd:
            setting.rabbitmq_pwd = rabbitmq_pwd
        elif setting.rabbitmq_pwd:
            rabbitmq_pwd = setting.rabbitmq_pwd
        else:
            logger.error("未配置RabbitMq密码")
            raise ValueError("未配置RabbitMq密码")
        try:
            Rabbit = RabbitMq.connect(name, rabbitmq_host=rabbitmq_host,
                                      rabbitmq_user=rabbitmq_user, rabbitmq_pwd=rabbitmq_pwd)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()
            os._exit(1)
        else:
            return Rabbit