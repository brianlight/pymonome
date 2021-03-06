# pymonome - library for interfacing with monome devices
#
# Copyright (c) 2011-2014 Artem Popov <artfwo@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import asyncio, aiosc
import itertools

__all__ = ['SerialOsc', 'Monome', 'BitBuffer']

def pack_row(row):
    return row[7] << 7 | row[6] << 6 | row[5] << 5 | row[4] << 4 | row[3] << 3 | row[2] << 2 | row[1] << 1 | row[0]

def unpack_row(val):
    return [
        val & 1,
        val >> 1 & 1,
        val >> 2 & 1,
        val >> 3 & 1,
        val >> 4 & 1,
        val >> 5 & 1,
        val >> 6 & 1,
        val >> 7 & 1
    ]

class Monome(aiosc.OSCProtocol):
    def __init__(self, prefix='python'):
        self.prefix = prefix.strip('/')
        self.id = None
        self.width = None
        self.height = None
        self.rotation = None

        super().__init__(handlers={
            '/sys/disconnect': lambda *args: self.disconnect,
            '/sys/{id,size,host,port,prefix,rotation}': self.sys_info,
            '/{}/grid/key'.format(self.prefix): lambda addr, path, x, y, s: self.grid_key(x, y, s),
            '/{}/tilt'.format(self.prefix): lambda addr, path, n, x, y, z: self.tilt(n, x, y, z),
        })

    def connection_made(self, transport):
        super().connection_made(transport)
        self.host, self.port = transport.get_extra_info('sockname')
        self.connect()

    def connect(self):
        self.send('/sys/host', self.host)
        self.send('/sys/port', self.port)
        self.send('/sys/prefix', self.prefix)
        self.send('/sys/info', self.host, self.port)

    def disconnect(self):
        self.transport.close()

    def sys_info(self, addr, path, *args):
        if path == '/sys/id':
            self.id = args[0]
        elif path == '/sys/size':
            self.width, self.height = (args[0], args[1])
        elif path == '/sys/rotation':
            self.rotation = args[0]

        # TODO: refine conditions for reinitializing
        # in case rotation, etc. changes
        # Note: arc will report 0, 0 for its size
        if all(x is not None for x in [self.id, self.width, self.height, self.rotation]):
            self.ready()

    def ready(self):
        pass

    def grid_key(self, x, y, s):
        pass

    def tilt(self, n, x, y, z):
        pass

    def led_set(self, x, y, s):
        self.send('/{}/grid/led/set'.format(self.prefix), x, y, s)

    def led_all(self, s):
        self.send('/{}/grid/led/all'.format(self.prefix), s)

    def led_map(self, x_offset, y_offset, data):
        args = [pack_row(data[i]) for i in range(8)]
        self.send('/{}/grid/led/map'.format(self.prefix), x_offset, y_offset, *args)

    def led_row(self, x_offset, y, data):
        args = [pack_row(data[i*8:(i+1)*8]) for i in range(len(data) // 8)]
        self.send('/{}/grid/led/row'.format(self.prefix), x_offset, y, *args)

    def led_col(self, x, y_offset, data):
        args = [pack_row(data[i*8:(i+1)*8]) for i in range(len(data) // 8)]
        self.send('/{}/grid/led/col'.format(self.prefix), x, y_offset, *args)

    def led_intensity(self, i):
        self.send('/{}/grid/led/intensity'.format(self.prefix), i)

    def led_level_set(self, x, y, l):
        self.send('/{}/grid/led/level/set'.format(self.prefix), x, y, l)

    def led_level_all(self, l):
        self.send('/{}/grid/led/level/all'.format(self.prefix), l)

    def led_level_map(self, x_offset, y_offset, data):
        self.send('/{}/grid/led/level/map'.format(self.prefix), x_offset, y_offset, *data)

    def led_level_row(self, x_offset, y, data):
        self.send('/{}/grid/led/level/row'.format(self.prefix), x_offset, y, *data)

    def led_level_col(self, x, y_offset, data):
        self.send('/{}/grid/led/level/col'.format(self.prefix), x, y_offset, *data)

    def tilt_set(self, n, s):
        self.send('/{}/tilt/set'.format(self.prefix), n, s)

class BitBuffer:
    def __init__(self, width, height):
        self.leds = [[0 for col in range(width)] for row in range(height)]
        self.width = width
        self.height = height

    def __and__(self, other):
        result = BitBuffer(self.width, self.height)
        for row in range(self.height):
            for col in range(self.height):
                result.leds[row][col] = self.leds[row][col] & other.leds[row][col]
        return result

    def __xor__(self, other):
        result = BitBuffer(self.width, self.height)
        for x in range(self.width):
            for y in range(self.height):
                result.leds[row][col] = self.leds[row][col] ^ other.leds[row][col]
        return result

    def __or__(self, other):
        result = BitBuffer(self.width, self.height)
        for x in range(self.width):
            for y in range(self.height):
                result.leds[row][col] = self.leds[row][col] | other.leds[row][col]
        return result

    def led_set(self, x, y, s):
        if x < self.width and y < self.height:
            row, col = y, x
            self.leds[col][row] = s

    def led_all(self, s):
        for x in range(self.width):
            for y in range(self.height):
                row, col = y, x
                self.leds[row][col] = s

    def led_map(self, x_offset, y_offset, data):
        for r, row in enumerate(data):
            self.led_row(x_offset, y_offset + r, row)

    def led_row(self, x_offset, y, data):
        for x, s in enumerate(data):
            self.led_set(x_offset + x, y, s)

    def led_col(self, x, y_offset, data):
        for y, s in enumerate(data):
            self.led_set(x, y_offset + y, s)

    def get_map(self, x_offset, y_offset):
        m = []
        for y in range(y_offset, y_offset + 8):
            row = []
            for x in range(x_offset, x_offset + 8):
                row.append(self.leds[x][y])
            m.append(row)
        return m

class Page:
    def __init__(self, app):
        self.app = app
        self.intensity = 15

    def ready(self):
        self._buffer = BitBuffer(self.width, self.height)

    def led_set(self, x, y, s):
        self._buffer.led_set(x, y, s)
        if self is self.app.current_page and not self.app.switching:
            self.app.led_set(x, y, s)

    def led_all(self, s):
        self._buffer.led_all(s)
        if self is self.app.current_page and not self.app.switching:
            self.app.led_all(s)

    def led_map(self, x_offset, y_offset, data):
        self._buffer.led_map(x_offset, y_offset, data)
        if self is self.app.current_page and not self.app.switching:
            self.app.led_map(x_offset, y_offset, data)

    def led_row(self, x_offset, y, data):
        self._buffer.led_row(x_offset, y, data)
        if self is self.app.current_page and not self.app.switching:
            self.app.led_row(x_offset, y, data)

    def led_col(self, x, y_offset, data):
        self._buffer.led_col(x, y_offset, data)
        if self is self.app.current_page and not self.app.switching:
            self.app.led_col(x, y_offset, data)

    def led_intensity(self, i):
        self.intensity = i
        if self is self.app.current_page and not self.app.switching:
            self.app.led_intensity(i)

from enum import Enum
class PageCorner(Enum):
    top_left = 1
    top_right = 2
    bottom_left = 3
    bottom_right = 4

class Pages(Monome):
    def __init__(self, pages, switch=PageCorner.top_right):
        super().__init__('/pages')
        self.pages = pages
        self.current_page = self.pages[0]
        self.switching = False
        self.pressed_buttons = []
        self.switch = switch

    def ready(self):
        for p in self.pages:
            p.width = self.width
            p.height = self.height
            p.ready()

        if self.switch == PageCorner.top_left:
            self.switch_button = (0, 0)
        elif self.switch == PageCorner.top_right:
            self.switch_button = (self.width - 1, 0)
        elif self.switch == PageCorner.bottom_left:
            self.switch_button = (0, self.height - 1)
        elif self.switch == PageCorner.bottom_right:
            self.switch_button = (self.width - 1, self.height - 1)
        else:
            raise RuntimeError

    def disconnect(self, *args):
        for p in self.pages:
            p.disconnect()

    def grid_key(self, x, y, s):
        if (x, y) == self.switch_button:
            if s == 1:
                # flush remaining presses
                for x, y in self.pressed_buttons:
                    self.current_page.grid_key(x, y, 0)
                # render selector page and set choose mode
                self.switching = True
                self.display_chooser()
            else:
                self.switching = False
                # TODO: ideally we only need to send key-ups if page changed
                # but if non-page mode key-up happened during switching,
                # it still has to be sent to original page
                self.leave_chooser()
            return
        if self.switching:
            pass # set current page based on coords
            if x < len(self.pages):
                self.current_page = self.pages[x]
                self.display_chooser()
            return
        # remember pressed buttons so we can flush them later
        if s == 1:
            self.pressed_buttons.append((x, y))
        else:
            # TODO: still getting x not in list errors here
            self.pressed_buttons.remove((x, y))
        self.current_page.grid_key(x, y, s)

    def display_chooser(self):
        self.led_all(0)
        page_row = [1 if i < len(self.pages) else 0 for i in range(self.width)]
        page_num = self.pages.index(self.current_page)
        self.led_row(0, self.height - 1, page_row)
        self.led_col(page_num, 0, [1] * self.height)

    def leave_chooser(self):
        for x_offset in [i * 8 for i in range(self.width // 8)]:
            for y_offset in [i * 8 for i in range(self.height // 8)]:
                led_map = self.current_page._buffer.get_map(x_offset, y_offset)
                self.led_map(0, 0, led_map)

class BaseSerialOsc(aiosc.OSCProtocol):
    def __init__(self):
        super().__init__(handlers={
            '/serialosc/device': self.serialosc_device,
            '/serialosc/add': self.serialosc_add,
            '/serialosc/remove': self.serialosc_remove,
        })
        self.devices = {}

    def connection_made(self, transport):
        super().connection_made(transport)
        self.host, self.port = transport.get_extra_info('sockname')

        self.send('/serialosc/list', self.host, self.port)
        self.send('/serialosc/notify', self.host, self.port)

    def device_added(self, id, type, port):
        self.devices[id] = port

    def device_removed(self, id, type, port):
        del self.devices[id]

    def serialosc_device(self, addr, path, id, type, port):
        self.device_added(id, type, port)

    def serialosc_add(self, addr, path, id, type, port):
        self.device_added(id, type, port)
        self.send('/serialosc/notify', self.host, self.port)

    def serialosc_remove(self, addr, path, id, type, port):
        self.device_removed(id, type, port)
        self.send('/serialosc/notify', self.host, self.port)

class SerialOsc(BaseSerialOsc):
    def __init__(self, apps, loop=None):
        super().__init__()
        self.apps = apps

        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

    def device_added(self, id, type, port):
        super().device_added(id, type, port)

        if id in self.apps:
            asyncio.async(self.autoconnect(self.apps[id], port))
        elif '*' in self.apps:
            asyncio.async(self.autoconnect(self.apps['*'], port))

    @asyncio.coroutine
    def autoconnect(self, app, port):
        transport, app = yield from self.loop.create_datagram_endpoint(
            app,
            local_addr=('127.0.0.1', 0),
            remote_addr=('127.0.0.1', port)
        )

    def device_removed(self, id, type, port):
        super().device_removed(id, type, port)

        if id in self.apps:
            self.apps[id].disconnect()
            del self.apps[id]
        elif '*' in self.apps:
            self.apps['*'].disconnect()
            del self.apps['*']

@asyncio.coroutine
def create_serialosc_connection(app_or_apps, loop=None):
    if isinstance(app_or_apps, dict):
        apps = app_or_apps
    else:
        apps = {'*': app_or_apps}

    if loop is None:
        loop = asyncio.get_event_loop()

    transport, serialosc = yield from loop.create_datagram_endpoint(
        lambda: SerialOsc(apps),
        local_addr=('127.0.0.1', 0),
        remote_addr=('127.0.0.1', 12002)
    )
    return serialosc
