
import sys
import signal
import logging
import configparser
import argparse
import json
from functools import partial
from tornado import ioloop, httpclient

import sysfs

__all__ = ('DEFAULT_CONFIG_LOCATION', 'DEFAULT_CONFIG_STUB',
           'main','run','io_callback','write_config')


DEFAULT_CONFIG_LOCATION='config.ini'
DEFAULT_CONFIG_STUB= {
                'post_url': 'http://ops.voltserver.dev/policy_input/state',
                'this_host': 'ioboard0',
                'enabled_pins': '408 409', # see: http://docs.getchip.com/#how-the-system-sees-gpio
            }

if __name__ == '__main__':
    logging.basicConfig(
            format='%(asctime)s %(levelname)s %(message)s',
            level=logging.DEBUG )

logger = logging.getLogger(__name__)

def io_callback(config, pin, value):
    '''
    Send an HTTP POST to C{config['post_url']} with JSON body in the form:
    {
        host: 'ioboard0', // name identifying this device, from config['this_host']
        input_id: 'd408', // pin ID
        value: 1          // changed value
    }
    '''
    logger.debug('PIN[%d] %d', pin.number, int(value) )

    post_body = json.dumps({
            'host': config['this_host'],
            'input_id': 'd%d' % pin.number, # d0, d1, etc. TODO analog input support
            'value': value,
        })

    # POST data to the server
    http = httpclient.AsyncHTTPClient()
    http.fetch(config['post_url'],
               callback=partial(handle_http_response, config, pin),
               headers={
                   'content-type':'application/json',
                   'accept':'application/json',
               },
               method='POST',
               body=post_body )

    logger.debug('HTTP >> [%s] %s', config['post_url'], post_body)


def handle_http_response(config, pin, response):
    if response.error:
        logger.warn('HTTP << %d %s', response.code, response.error)
        return

    logger.debug('HTTP << %d %s', response.code, response.body)


def read_config( location=DEFAULT_CONFIG_LOCATION ):
    config = configparser.ConfigParser()
    with open(location,'r') as file:
        config.read_file(file)
    return config


def write_default_config( location=DEFAULT_CONFIG_LOCATION ):
    '''
    Write a default config file to C{DEFAULT_CONFIG_LOCATION}.
    Default config will look like:

    [main]
    post_url: http://foo.com/policy_input/state
    this_host: ioboard0
    enabled_pins: 1 2 3

    See C{DEFAULT_CONFIG_STUB}
    '''
    config = configparser.ConfigParser()
    config['main'] = DEFAULT_CONFIG_STUB

    with open(location,'w') as file:
        config.write(file)


def main(args):
    '''
    Parse cmd line opts, read config & call C{run()}
    '''

    if args.write_config:
        print('Writing default config file to %s' % args.config)
        write_default_config(args.config)
        sys.exit(1)

    # else parse config and run main loop:
    config = read_config(args.config)
    run(config['main'])  # TODO option to select alternate config section?


def run(config):
    io_loop = ioloop.IOLoop.current()

    def quit(sig,frame):
        logger.info("Caught signal (%d), quitting...", sig)
        io_loop.stop()

    for sig in ('HUP','INT','QUIT','TERM'):
        signal.signal( getattr(signal, 'SIG'+sig), quit )


    # assume all enabled pins are inputs.
    pins = list(map(int, config['enabled_pins'].split()))
    gpio = sysfs.Gpio( poll_queue=io_loop,
                        available_pins=pins )

    callback = partial(io_callback, config)
    for pin in pins:
        logger.debug('PIN %d enabled as input', pin)
        gpio.alloc_pin(pin, sysfs.INPUT, callback, sysfs.BOTH)

    io_loop.start()


parser = argparse.ArgumentParser(description='SysFS GPIO poller/ HTTP forwarder')
parser.add_argument('-c', '--config', default=DEFAULT_CONFIG_LOCATION,
        help='Config file to use (absolute path or relative to working dir)' )
parser.add_argument('--write-config', action='store_const', const=True,
        help='write a config file stub and exit')

if __name__ == '__main__':
    main(parser.parse_args())
