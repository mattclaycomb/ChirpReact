import logging
import tornado.auth
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
import os.path
import uuid
import time
import random
import pika
import json
import redis
from xml.dom.minidom import parseString
from pika.adapters.tornado_connection import TornadoConnection
from tradeking import TradeKingMixin
import chirpreact_settings

from tornado import httpclient
from tornado.options import define, options

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/symbolws", SymbolWebSocket),
            (r"/", MainHandler),
            (r"/login", TestHandler),
            (r"/stock_info/([A-Z]+)", StockInfoHandler),
            (r"/quick_order", QuickOrderHandler),
            (r"/initial_symbols", InitialSymbolsHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
        ]
        settings = dict(
            login_url="/auth/login",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            autoescape="xhtml_escape",
            debug=True
        )
        settings.update(chirpreact_settings.settings)
        tornado.web.Application.__init__(self, handlers, **settings)

class PikaClient(object):
    def __init__(self):
        self.connected = False
        self.connection = None
        self.channel = None
        self.messages = list()

    def connect(self):
        self.connection = TornadoConnection(on_open_callback=self.on_connected)

    def on_connected(self, connection):
        self.connected = True
        self.connection = connection
        self.connection.channel(self.on_channel_open)

    def on_channel_open(self, channel):
        pika.log.info("channel open")
        self.channel = channel

class SymbolWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        queue = application.pika.channel.queue_declare(callback=self.on_queue_declared)

    def on_queue_declared(self, frame):
        application.pika.channel.queue_bind(exchange="stocktweets", queue=frame.method.queue)
        self.consumer_tag = application.pika.channel.basic_consume(consumer_callback=self.callback,
            no_ack=True,
            queue=frame.method.queue)

    def callback(self, channel, method, header, body):
        self.write_message(body)

    def on_close(self):
        application.pika.channel.basic_cancel(self.consumer_tag)

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if not user_json: return None
        return tornado.escape.json_decode(user_json)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class QuickOrderHandler(BaseHandler, TradeKingMixin):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def post(self):
        account = "0" # This shouldn't be hardcoded
        symbol = self.get_argument("symbol")
        quantity = self.get_argument("quantity")
        buy_or_sell = self.get_argument("buyOrSell")
        access_token = self.settings['tradeking_access_token']
        self.tradeking_order_request(self.on_results, access_token, account, symbol, quantity, buy_or_sell)

    def on_results(self, results):
        self.write(tornado.escape.json_encode(results))
        self.finish()

class InitialSymbolsHandler(BaseHandler, TradeKingMixin):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        access_token = self.settings['tradeking_access_token']
        self.tradeking_request('/watchlists/DEFAULT', self.on_results, access_token)

    def on_results(self, results):
        screen_name = self.get_current_user()['screen_name']
        watchlist_symbols = []
        application.redis.delete("watchlist_symbols_"+screen_name)
        for watchlistitem in results['response']['watchlists']['watchlist']['watchlistitem']:
            watchlist_symbols.append({'id': watchlistitem['instrument']['sym'], 'value': 0})
            application.redis.sadd("watchlist_symbols_"+screen_name, watchlistitem['instrument']['sym'])
        self.write(tornado.escape.json_encode(watchlist_symbols))   
        self.finish()

class StockInfoHandler(BaseHandler, TradeKingMixin):
    @tornado.web.asynchronous
    def get(self, symbol):
        self.symbol = symbol
        http = httpclient.AsyncHTTPClient()
        url = "http://finance.yahoo.com/rss/headline?s=" + symbol
        http.fetch(url, self.on_rss_feed)

    def on_rss_feed(self, response):
        if response.error:
            logging.warning("Error response %s fetching %s", response.error,
                            response.request.url)
            return
        self.rss_feed = parseString(response.body)
        access_token = self.settings['tradeking_access_token']
        self.tradeking_request('/market/quotes', self.on_results, access_token, symbols=self.symbol)

    def on_results(self, results):
        self.render("stock_info.html", symbol=self.symbol, results=results['response'], rss_feed=self.rss_feed)

class TestHandler(BaseHandler, TradeKingMixin):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        sn = self.get_current_user()['screen_name']
        self.write("You are authenticated if you can see this, "+sn+"!")

        access_token = self.settings['tradeking_access_token']
        self.tradeking_request('/accounts', self.on_results, access_token)

    def on_results(self, new_tweet):
        self.write(str(new_tweet))
        self.finish()

class AuthLoginHandler(BaseHandler, tornado.auth.TwitterMixin):
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("oauth_token", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authorize_redirect('http://'+self.request.headers['Host']+'/auth/login')

    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Twitter auth failed")
        self.set_secure_cookie("user", tornado.escape.json_encode(user))
        application.redis.set(user['screen_name'],
            tornado.escape.json_encode(user['access_token']))
        application.pika.channel.basic_publish(exchange='', routing_key='login_queue',
            body=tornado.escape.json_encode(user['access_token']))
        self.redirect("/")

class AuthLogoutHandler(BaseHandler):
    def get(self):
        application.redis.delete(self.get_current_user()['screen_name'])
        self.clear_cookie("user")
        self.write("You are now logged out")

logging.basicConfig(level=logging.DEBUG)
application = Application()
application.pika = PikaClient()
application.redis = redis.StrictRedis(host='localhost', port=6379, db=0)

if __name__ == "__main__":
    #tornado.options.parse_command_line()
    application.listen(8888)
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.add_timeout(500, application.pika.connect)
    ioloop.start()
