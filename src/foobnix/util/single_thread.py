#-*- coding: utf-8 -*-
'''
Created on 27 сент. 2010

@author: ivan
'''
import thread
from threading import Lock
from foobnix.util import LOG
import time

class SingleThread():
    def __init__(self, progressbar):
        self.lock = Lock()
        self.progressbar = progressbar
    
    def run_with_progressbar(self, method, args=None, text=None, no_thread=False):
        if no_thread:
            if method and args:
                method(args)
            if method:
                method()                            
        else:
            self.progressbar.start(text)
            self._run(method, args)
    
    def _run(self, method, args=None):
        if not self.lock.locked():            
            self.lock.acquire()            
            thread.start_new_thread(self._thread_task, (method, args,))
        else:
            LOG.warn("Thread not finished", method, args)    
    
    def _thread_task(self, method, args):
        try:
            if method and args:
                method(args)
            elif method:
                method()
            time.sleep(0.1)
        except Exception, e:
            LOG.error(e)
        finally:
            self.progressbar.stop()        
            self.lock.release()