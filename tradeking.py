import base64
import binascii
import hashlib
import hmac
import logging
import time
import urllib
import urlparse
import uuid

from tornado import httpclient
from tornado import escape
from tornado.httputil import url_concat
from tornado.util import bytes_type, b
from tornado.auth import OAuthMixin

# Full OAuth wasn't implemented because it needs special permission from TradeKing
class TradeKingMixin(OAuthMixin):
    _OAUTH_REQUEST_TOKEN_URL = "http://developers.tradeking.com/oauth/request_token"
    _OAUTH_ACCESS_TOKEN_URL = "http://developers.tradeking.com/oauth/access_token"
    _OAUTH_AUTHORIZE_URL = "http://developers.tradeking.com/oauth/authorize"
    #_OAUTH_AUTHENTICATE_URL = "http://api.twitter.com/oauth/authenticate"
    _OAUTH_NO_CALLBACKS = False
    _OAUTH_VERSION = "1.0"

    def tradeking_request(self, path, callback, access_token=None,
                          post_args=None, **args): 
        """Fetches given path from Tradeking"""
        url = "https://api.tradeking.com/v1" + path + ".json"
        if access_token:
            all_args = {}
            all_args.update(args)
            all_args.update(post_args or {})
            method = "POST" if post_args is not None else "GET"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args: url += "?" + urllib.urlencode(args)
        callback = self.async_callback(self._on_tradeking_request, callback)
        http = httpclient.AsyncHTTPClient()
        if post_args is not None:
            http.fetch(url, method="POST", body=urllib.urlencode(post_args),
                       callback=callback)
        else:
            http.fetch(url, callback=callback)

    def tradeking_order_request(self, callback, access_token, account, symbol,
                                quantity, buy_or_sell, **args): 
        """Places fake order for Tradeking"""
        path = "/accounts/"+account+"/orders/preview"
        url = "https://api.tradeking.com/v1" + path + ".json"
        if access_token:
            all_args = {}
            all_args.update(args)
            method = "POST"
            oauth = self._oauth_request_parameters(
                url, access_token, all_args, method=method)
            args.update(oauth)
        if args: url += "?" + urllib.urlencode(args)
        bstype = "2" if buy_or_sell == "sell" else "1"

        body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?> \
         <FIXML xmlns=\"http://www.fixprotocol.org/FIXML-5-0-SP2\"> \
           <Order TmInForce=\"0\" Typ=\"1\" Side=\"{}\" Acct=\"{}\"> \
           <Instrmt SecTyp=\"CS\" Sym=\"{}\"/> \
           <OrdQty Qty=\"{}\"/> \
           </Order> \
         </FIXML>".format(bstype, account, symbol, quantity)

        callback = self.async_callback(self._on_tradeking_request, callback)
        http = httpclient.AsyncHTTPClient()
        http.fetch(url, method="POST", body=body,
                   callback=callback)

    def _on_tradeking_request(self, callback, response):
        if response.error:
            logging.warning("Error response %s fetching %s", response.error,
                            response.request.url)
            callback(None)
            return
        callback(escape.json_decode(response.body))

    def _oauth_consumer_token(self):
        self.require_setting("tradeking_consumer_key", "TradeKing OAuth")
        self.require_setting("tradeking_consumer_secret", "TradeKing OAuth")
        return dict(
            key=self.settings["tradeking_consumer_key"],
            secret=self.settings["tradeking_consumer_secret"])
