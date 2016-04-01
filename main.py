
import sys
import signal
import logging
import configparser
import argparse
import json
from functools import partial
from tornado import ioloop, httpclient

import sysfs

DEFAULT_CONFIG_LOCATION='config.ini'

if __name__ == '__main__':
    logging.basicConfig(
            format='%(asctime)s %(levelname)s %(message)s',
            level=logging.DEBUG )

logger = logging.getLogger(__name__)


def io_callback(config, pin, value):
    Logger.debug('PIN[%d] %d', pin.number, int(value) )

    post_body = json.dumps({
            'id': config['id'],
            'pin': pin.number,
            'value': value,
        })

    # POST data to the server
    http = httpclient.AsyncHTTPClient()
    http.fetch(config['url'],
               callback=partial(handle_http_response, config, pin),
               headers={
                   'content-type':'application/json',
               },
               method='POST',
               body=post_body )

    logger.debug('HTTP [%s] >> %s', config['url'], post_body)


def handle_http_response(config, pin, response):
    logger.debug('HTTP << %d %s', response.code, response.body)


def read_config( location=DEFAULT_CONFIG_LOCATION ):
    config = configparser.ConfigParser()
    with open(location,'r') as file:
        config.read_file(file)
    return config


def write_default_config( location=DEFAULT_CONFIG_LOCATION ):
    config = configparser.ConfigParser()
    config['main'] = {
                'url': 'http://ops.voltserver.dev/ioboard-http',
                'id': 'http-ioboard0',
                'enabled_pins': '1 2 3'
            }

    with open(location,'w') as file:
        config.write(file)


def main(args):
    if args.write_config:
        print('Writing default config file to %s' % args.config)
        write_default_config(args.config)
        sys.exit(1)

    # else parse config and run main loop:
    config = read_config(args.config)
    run(config['main'])


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
        help='Config file to use' )
parser.add_argument('--write-config', action='store_const', const=True,
        help='write a config file stub and exit')

if __name__ == '__main__':
    main(parser.parse_args())
