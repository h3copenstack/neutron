# -*- coding: utf-8 -*-
#
# H3C Technologies Co., Limited Copyright 2003-2015, All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import threading
import time
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class Timer(object):
    def __init__(self, timeout, is_periodical=True):
        self.delay = timeout
        self.is_periodical = is_periodical
        self.callback = None
        self.timer_thread = GreenThread(self._inner)
        self.timer_thread.setDaemon(True)
        self.waiter = self.timer_thread.get_waiter()
        self.lock = self.timer_thread.get_lock()
        self.is_running = is_periodical
        self.f = None
        self.args = None
        self.kwargs = None
        self.is_first_init = True

    def _inner(self):
        if self.is_first_init:
            if self.waiter.wait(self.delay):
                self.waiter.clear()
                return
            if self.is_running is not True:
                self.f(*self.args, **self.kwargs)

        while self.is_running:
            start = time.time()
            self.f(*self.args, **self.kwargs)
            end = time.time()
            delay = self.delay - (end - start)
            if delay < 0:
                LOG.warn('%s run time is beyond delay time.' % self.f)
            if self.waiter.wait(delay if delay > 0 else 0):
                self.waiter.clear()
        LOG.info('Timer is stop.')

    def stop(self):
        self.is_running = False
        self.waiter.set()

    def start(self, callback, *args, **kwargs):
        self.f = callback
        self.args = args
        self.kwargs = kwargs
        self.timer_thread.start()

    def get_lock(self):
        return self.lock


class GreenThread(threading.Thread):
    def __init__(self, callback=None, *args, **kwargs):
        super(GreenThread, self).__init__()
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.callback = callback
        self.args = args
        self.kwargs = kwargs

    def get_waiter(self):
        return self.event

    def run(self):
        if self.callback is not None:
            self.callback(*self.args, **self.kwargs)

    def get_lock(self):
        return self.lock
