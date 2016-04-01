"""
Linux SysFS-based native GPIO implementation.

The MIT License (MIT)

Copyright (c) 2014 Derek Willian Stavis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__all__ = ('DIRECTIONS', 'INPUT', 'OUTPUT',
           'EDGES', 'RISING', 'FALLING', 'BOTH',
           'Gpio')

import os
import logging
from functools import partial
from tornado.ioloop import IOLoop

from .pin import Pin

logger = logging.getLogger(__name__)

# Sysfs constants

SYSFS_BASE_PATH     = '/sys/class/gpio'

SYSFS_EXPORT_PATH   = SYSFS_BASE_PATH + '/export'
SYSFS_UNEXPORT_PATH = SYSFS_BASE_PATH + '/unexport'

SYSFS_GPIO_PATH           = SYSFS_BASE_PATH + '/gpio%d'

EPOLL_TIMEOUT = 1  # second

# Public interface

INPUT   = 'in'
OUTPUT  = 'out'

RISING  = 'rising'
FALLING = 'falling'
BOTH    = 'both'

DIRECTIONS = (INPUT, OUTPUT)
EDGES = (RISING, FALLING, BOTH)


class Gpio(object):

    def __init__(self, poll_queue=None, available_pins=[]):
        if not poll_queue:
            poll_queue = IOLoop.current()
            logger.debug('SysfsGPIO: using default IOLoop %s', poll_queue)

        self._poll_queue = poll_queue
        self._allocated_pins = {}
        self._available_pins = available_pins

    @property
    def available_pins(self):
        return self._available_pins

    @available_pins.setter
    def available_pins(self, value):
        self._available_pins = value

    def alloc_pin(self, number, direction, callback=None, edge=None, active_low=0):

        logger.debug('SysfsGPIO: alloc_pin(%d, %s, %s, %s, %s)'
                     % (number, direction, callback, edge, active_low))

        self._check_pin_validity(number)

        if direction not in DIRECTIONS:
            raise Exception("Pin direction %s not in %s"
                            % (direction, DIRECTIONS))

        if callback and edge not in EDGES:
            raise Exception("Pin edge %s not in %s" % (edge, EDGES))

        if not self._check_pin_already_exported(number):
            with open(SYSFS_EXPORT_PATH, 'w') as export:
                export.write('%d' % number)
        else:
            logger.debug("SysfsGPIO: Pin %d already exported" % number)

        pin = Pin(number, direction, callback, edge, active_low)

        if direction is INPUT:
            self._poll_queue_register_pin(pin)

        self._allocated_pins[number] = pin
        return pin


    def dealloc_pin(self, number):
        logger.debug('SysfsGPIO: dealloc_pin(%d)' % number)

        if number not in self._allocated_pins:
            raise Exception('Pin %d not allocated' % number)

        with open(SYSFS_UNEXPORT_PATH, 'w') as unexport:
            unexport.write('%d' % number)

        pin = self._allocated_pins[number]

        if pin.direction is INPUT:
            self._poll_queue_unregister_pin(pin)

        del pin, self._allocated_pins[number]


    def get_pin(self, number):
        logger.debug('SysfsGPIO: get_pin(%d)' % number)

        return self._allocated_pins[number]


    def set_pin(self, number):
        logger.debug('SysfsGPIO: set_pin(%d)' % number)

        if number not in self._allocated_pins:
            raise Exception('Pin %d not allocated' % number)

        return self._allocated_pins[number].set()


    def reset_pin(self, number):
        logger.debug('SysfsGPIO: reset_pin(%d)' % number)

        if number not in self._allocated_pins:
            raise Exception('Pin %d not allocated' % number)

        return self._allocated_pins[number].reset()


    def get_pin_state(self, number):
        logger.debug('SysfsGPIO: get_pin_state(%d)' % number)

        if number not in self._allocated_pins:
            raise Exception('Pin %d not allocated' % number)

        pin = self._allocated_pins[number]

        if pin.direction == INPUT:
            self._poll_queue_unregister_pin(pin)

        val = pin.read()

        if val <= 0:
            return False
        else:
            return True


    ''' Private Methods '''

    def _poll_queue_register_pin(self, pin):
        ''' Pin responds to fileno(), so it's pollable. '''
        callback = partial(self._poll_queue_event, pin)
        self._poll_queue.add_handler(pin, callback, io_loop.READ|io_loop._EPOLLET)


    def _poll_queue_unregister_pin(self, pin):
        self._poll_queue.remove_handler(pin)


    def _poll_queue_event(self, pin, fd, events):
        """
        EPoll event callback
        """

        pin.changed(pin.read())


    def _check_pin_already_exported(self, number):
        """
        Check if this pin was already exported on sysfs.

        @type  number: int
        @param number: Pin number
        @rtype: bool
        @return: C{True} when it's already exported, otherwise C{False}
        """
        gpio_path = SYSFS_GPIO_PATH % number
        return os.path.isdir(gpio_path)


    def _check_pin_validity(self, number):
        """
        Check if pin number exists on this bus

        @type  number: int
        @param number: Pin number
        @rtype: bool
        @return: C{True} when valid, otherwise C{False}
        """

        if number not in self._available_pins:
            raise Exception("Pin number (%s) out of range" % number)

        if number in self._allocated_pins:
            raise Exception("Pin (%s) already allocated" % number)


