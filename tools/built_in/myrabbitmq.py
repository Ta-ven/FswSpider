import threading
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
        logger.debug("心态线程开始！")
        self.lock.acquire()
        if self.quitflag:
            self.lock.release()
            return
        self.stopflag = False
        self.lock.release()


class RabbitMq:
    def __init__(self, name, connection, channel, queue):
        self.name = name
        self.rabbitmq_host = setting.rabbitmq_host
        self.rabbitmq_pwd = setting.rabbitmq_pwd
        self.connection = connection
        self.channel = channel
        self.queue = queue

    @classmethod
    def connect(cls, name, is_count=False):
        if not is_count:
            logger.debug("开始连接rabbitmq队列！")
            user_pwd = pika.PlainCredentials(setting.rabbitmq_user, setting.rabbitmq_pwd)
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=setting.rabbitmq_host, credentials=user_pwd))
            channel = connection.channel()
            queue = channel.queue_declare(queue=name, durable=True,)
            return cls(name, connection, channel, queue)
        else:
            res = requests.get(url='http://{}:{}/api/queues/{}/{}'.format(setting.rabbitmq_host, "15672", "%2F", name
                                                                          ), auth=(setting.rabbitmq_user,
                                                                                   setting.rabbitmq_pwd))
            res = json.loads(res.content.decode())
            return int(res["messages"])

    def pulish(self, body, priority=0):
        self.channel.basic_publish(exchange='', routing_key=self.name, body=body,
                                   properties=pika.BasicProperties(delivery_mode=2, priority=priority))

    def consume(self, callback=None, limit=1):
        self.channel.basic_qos(prefetch_count=limit)
        self.channel.basic_consume(queue=self.name, on_message_callback=callback)
        heartbeat = Heartbeat(self.connection)  # 实例化一个心跳类
        heartbeat.start()  # 开启一个心跳线程，不传target的值默认运行run函数
        heartbeat.startheartbeat()  # 开启心跳保护
        # self.channel.start_consuming()
        try:
            # consu = threading.Thread(target=self.channel.start_consuming, )  # 开始消费
            consu = ExceptErrorThread(self.channel.start_consuming)
            consu.setDaemon(True)
            consu.start()
            while True:
                consu.join(10)
                if RabbitMq.connect(self.name, is_count=True) == 0:
                    break
        except Exception as e:
            logger.error(consu.exc_traceback)

    def del_queue(self, name, if_unused=False, if_empty=False):
        self.channel.queue_delete(queue=name, if_unused=if_unused, if_empty=if_empty)

    def purge(self, name):
        self.channel.queue_purge(name)