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
from pika.adapters.tornado_connection import TornadoConnection
from tradeking import TradeKingMixin
import chirpreact_settings

from tornado.options import define, options

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/symbolws", SymbolWebSocket),
            (r"/", MainHandler),
            (r"/test", TestHandler),
            (r"/stock_info/([A-Z]+)", StockInfoHandler),
            (r"/quick_order", QuickOrderHandler),
            (r"/initial_symbols", InitialSymbolsHandler),
            (r"/storm", StormHandler),
            (r"/auth/login", AuthLoginHandler),
            (r"/auth/logout", AuthLogoutHandler),
        ]
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
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

        # place to put messages as they come in
        self.messages = list()

    def on_connected(self, connection):
        self.connected = True
        self.connection = connection
        self.connection.channel(self.on_channel_open)

    def on_channel_open(self, channel):
        pika.log.info("channel open")
        self.channel = channel
        #self.channel.queue_declare(queue="hello", callback=self.on_queue_declared)

    def on_queue_declared(self, frame):
        self.channel.basic_consume(consumer_callback=self.on_pika_message, queue="hello", no_ack=True)

    def on_pika_message(self, channel, method, header, body):
        import pdb; pdb.set_trace()
        pika.log.info("message recieved: "+body)
        self.messages.append(body)

    def connect(self):
        self.connection = TornadoConnection(on_open_callback=self.on_connected)

class SymbolWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        application.pika.channel.basic_consume(consumer_callback=self.callback,
            no_ack=True,
            queue="test")

    def callback(self, channel, method, header, body):
        self.write_message(body)

    def on_close(self):
        #application.pika.channel.basic_cancel(method.consumer_tag)
        pass

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
        account = "60726353"
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

#class StockInfoHandler(BaseHandler, tornado.auth.TwitterMixin):
class StockInfoHandler(BaseHandler, TradeKingMixin):
    @tornado.web.asynchronous
    def get(self, symbol):
        self.symbol = symbol
        #access_token = self.get_current_user()['access_token']
        #self.twitter_request('/search', self.on_results, access_token, { 'q': "$"+symbol })
        access_token = self.settings['tradeking_access_token']
        self.tradeking_request('/market/quotes', self.on_results, access_token, symbols=symbol)

    def on_results(self, results):
        self.render("stock_info.html", symbol=self.symbol, results=results['response'])

class TestHandler(BaseHandler, TradeKingMixin):
#class TestHandler(BaseHandler, tornado.auth.TwitterMixin):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self):
        sn = self.get_current_user()['screen_name']
        self.write("You are authenticated if you can see this, "+sn+"!")

        access_token = self.settings['tradeking_access_token']
        self.tradeking_request('/accounts', self.on_results, access_token)
        #access_token = self.get_current_user()['access_token']
        #self.twitter_request('/users/lookup', self.on_results, access_token, { 'screen_name': "MattClaycomb" })

    def on_results(self, new_tweet):
        self.write(str(new_tweet))
        self.finish()

class StormHandler(BaseHandler):
    @tornado.web.asynchronous
    @tornado.web.authenticated
    def get(self):
        self.msg_list = []
        application.pika.channel.basic_consume(consumer_callback=self.callback,
            no_ack=True,
            queue="test")

    def callback(self, channel, method, header, body):
        print body
        self.msg_list.append(tornado.escape.json_decode(body))
        try:
            application.pika.channel.basic_cancel(method.consumer_tag, callback=self.finish_callback)
        except KeyError:
            pass

    def finish_callback(self, unknown):
        self.write(tornado.escape.json_encode(self.msg_list))
        self.finish()

class AuthLoginHandler(BaseHandler, tornado.auth.TwitterMixin):
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("oauth_token", None):
            print 'got here?'
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        import pdb; pdb.set_trace()
        self.authorize_redirect('http://'+self.request.headers['Host']+'/auth/login')

    def _on_auth(self, user):
        if not user:
            raise tornado.web.HTTPError(500, "Twitter auth failed")
        self.set_secure_cookie("user", tornado.escape.json_encode(user))
        application.redis.set(user['screen_name'],
            tornado.escape.json_encode(user['access_token']))
        self.redirect("/test")

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
