import hashlib
import traceback
import sys
import threading
import re
import setting
from selenium import webdriver
import time
from parsel import Selector
from selenium.webdriver.chrome.options import Options
import asyncio
from pyppeteer import launch


# url去重MD5
def get_md5(url):
    if isinstance(url, list) or isinstance(url, tuple):
        url = ''.join([str(u) if u else '' for u in url])
    m = hashlib.md5()
    if isinstance(url, str):
        url = url.encode('utf-8')
    m.update(url)
    return m.hexdigest()


def selector(res, encode=None):
    if hasattr(res, 'ok'):
        if encode:
            resp = Selector(res.content.decode(encode))
        else:
            apparent_encoding = res.apparent_encoding
            if '2312' in apparent_encoding or 'dows' in apparent_encoding or '8859' in apparent_encoding:
                apparent_encoding = 'gbk'
            try:
                resp = Selector(res.content.decode(apparent_encoding))
            except:
                resp = Selector(res.content.decode(apparent_encoding, 'ignore'))
    else:
        if isinstance(res, str):
            resp = Selector(res)
        else:
            resp = Selector(res.text)
    return resp

class ExceptErrorThread(threading.Thread):
    def __init__(self, funcName, *args):
        threading.Thread.__init__(self)
        self.args = args
        self.funcName = funcName
        self.exitcode = 0
        self.exception = None
        self.exc_traceback = ''

    def run(self):  # Overwrite run() method, put what you want the thread do here
        try:
            self._run()
        except Exception as e:
            self.exitcode = 1  # 如果线程异常退出，将该标志位设置为1，正常退出为0
            self.exception = e
            self.exc_traceback = ''.join(traceback.format_exception(*sys.exc_info()))  # 在改成员变量中记录异常信息

    def _run(self):
        try:
            self.funcName(*(self.args))
        except Exception as e:
            raise e


def get_cookies(url, headless=True, executable_path=None, proxy=None):
    """
    用selenium获取cookies
    :param url:
    :param headless: 是否需要无头
    :param executable_path: webdriver路径
    :param proxy: 代理
    :return: 字符串cookies，需要放在headers里
    """
    new_url = re.search("(http|https)://(www.)?(\w+(\.)?)+", url).group()
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument(
        'user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.3170.100 Safari/537.36"')
    if proxy:
        chrome_options.add_argument('--proxy-server=http://{}'.format(proxy))
    if executable_path:
        path = executable_path
    else:
        path = setting.webdriver_path_win
    browser1 = webdriver.Chrome(path, chrome_options=chrome_options)
    browser1.get(new_url)
    time.sleep(1)
    cookielist = browser1.get_cookies()
    cookie = ""
    for c in cookielist:
        name = c['name']
        value = c['value']
        if name not in cookie:
            cookie += (name + "=" + value + ";")
    cookie = cookie[:-1]
    browser1.close()
    browser1.quit()
    return cookie




if __name__ == '__main__':
    a = get_cookies("https://www.baidu.com/")
    print(a)