require 'rubygems'
require 'tweetstream'
require 'amqp'
require 'redis'
require 'json'
require 'ERB'

# This redis client is blocking, but the
# response are times are quick enough
redis = Redis.new

puts "Starting Twitter Client"
EventMachine.run do
  connection = AMQP.connect(:host=>'127.0.0.1')
  puts 'Connecting to broker...'
  channel = AMQP::Channel.new(connection)
  login_queue = channel.queue('login_queue')
  d_exchange = channel.default_exchange
  exchange = channel.fanout('stocktweets')
  
  # When a user logs in start thier twitter consumer,
  # publish tweets to the stocktweets exchange
  login_queue.subscribe do |payload|
    access_token = JSON.load(payload)

    TweetStream.configure do |config|
      config.consumer_key = 'f2KubELJJISvTFpEeAEvg'
      config.consumer_secret='BnE8IF8NoMq4ZnI6tIzwOSjGYzoncfdxjrFy1z0w'
      config.oauth_token= access_token['key']
      config.oauth_token_secret= access_token['secret']
      config.auth_method=:oauth
      config.parser=:yajl
    end

    symbols = redis.smembers("watchlist_symbols_"+access_token['screen_name'])[0..9].collect { |s| "$#{s}" }
    TweetStream::Client.new.track(symbols) do |status|
      symbols.each do |symbol|
          if status.text =~ Regexp.new('\\'+symbol)
              exchange.publish "{ \"id\": \"#{symbol.sub('$','')}\", \"status\": \"#{ERB::Util.html_escape(status.text)}\" }"
              puts "#{status.text}"
          end
      end
    end
  end
end
