ChirpReact
==========

ChirpReact was an assignment for a finance class I took Fall 2011.

There are 4 services necessary to run ChirpReact
* RabbitMQ - A message broker.
* Redis - A key-value store.
* ChirpReact Twitter Consumer
* ChirpReact Web Server

ChirpReact Twitter Consumer is built in Ruby. ChirpReact Twitter Consumer uses
EventMachine for asynchronous IO.

ChirpReact Web Server is built in python. It uses the Tornado web framework
(http://tornadoweb.org). Tornado websockets support is used to create a bidirectional
connection between the browser and server.


Installing ChirpReact Web Server
--------------------------------
1. Install python and pip
    * Tested with Python 2.7.1, it recommended to create a python virtualenv to get pip.
    (http://pypi.python.org/pypi/virtualenv)
2. Install dependencies required for project:
   pip install -r requirements.txt

3. python chirpreact_web_server.py 

Installing ChirpReact Twitter Consumer
--------------------------------------
1. Intall Ruby and bundler
    * Tested with Ruby 1.8.7p249. bundler can be installed with:
    gem install bundler
2. Install project dependencies with bundler:
   bundle install
3. Run Twitter Consumer:
   ruby chirpreact_twitter_consumer.rb

The website can be accessed by visiting http://localhost:8888/login
and logging in with your Twitter credentials.
