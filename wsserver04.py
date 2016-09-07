import tornado.ioloop, tornado.web, tornado.websocket, tornado.httpserver ,tornadoredis
import logging, json, urlparse, redis
import base64 as b64
from time import gmtime, strftime
from tornado.options import parse_command_line
from tornado import gen
from tornado.options import define,options

"""

**YouNoty**
Real time notification system for IM and push notification based on tornado and redis
orsidev on https://github.com/orsi-dev

"""
REDIS_SERVER = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 1
REDIS_CHANNEL = None

logging.basicConfig(filename='YouMsg.log', format='%(asctime)s %(message)s', level=log.DEBUG, filemode="a+") #configurazione file log


#logging = logging.getLogger('base.tornado')

# store clients in dictionary..
clients = dict()

pool = tornadoredis.ConnectionPool(host=REDIS_SERVER, port=REDIS_PORT, max_connections=20, wait_for_available=True)

"""

SENDER Handler

127.0.0.0.1:8888/msg?message={"client_id":"158","att_id":"13", "msg":"hello there"}

if client is offline store notification into redis list
else send publish command with message to subscriber


"""

#metodo di conversione da base64
def base64decoder_(string):
   """
       base64 decoder for sender and receiver strings
       :type string: object
   """
   base_decode = string
   decoded = b64.b64decode(base_decode)
   return decoded



class NewMessage(tornado.web.RequestHandler): #TODO convert json into base64 with base64decoder_

    def check_origin(self, origin):
        """
            Check if incoming connection is in supported domain
            :param origin (str): Origin/Domain of connection
        """
        return True

    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self):
        """
            method get to send the value of querystring argument (:message)
            and publish data into redis channel or save into a list

        """
        self.message = self.get_argument('message')
        queryParDecoded = base64decoder_(str(self.message))
        body_ = json.loads(eval(queryParDecoded))
        #appendo i nuovi dati al json
        body_["created_at"] = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        k = list(clients.keys())

        namespace_Redis_List = str(body_['att_id'])+':'+str(body_['client_id'])

        if body_['client_id'] in k: #se l' utente a cui si vuole inviare il msg e' loggato

            with tornadoredis.Client(connection_pool=pool) as c:

                foo = yield tornado.gen.Task(c.publish, str(body_['att_id']), message)
                self.write('sent: %s' % (message))
                self.finish(str(foo))

        else: #altrimenti vai a scrivere su una lista di redis
                body_["ricevuta"] = 0
                r = redis.StrictRedis(host=REDIS_SERVER, port=REDIS_PORT, db=REDIS_DB)
                r.lpush(namespace_Redis_List, json.dumps(body_))
                self.write('sent: %s' % (json.dumps(body_)))
                self.finish(str(r))

'''

RECEIVER Handler

Json sample for subscription
{"client_id" : "1","att_id" : "13"} = eyJjbGllbnRfaWQiIDogIjEiLCJhdHRfaWQiIDogIjEzIn0=

127.0.0.1:{websocketport}/ws-noty?UID=eyJjbGllbnRfaWQiIDogIjEiLCJhdHRfaWQiIDogIjEzIn0=


'''


class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):

        self.client_id = None
        self._redis_client = None
        super(WebSocketHandler, self).__init__(*args, **kwargs)
        qrs = self.get_argument("UID")
        queryParDecoded = base64decoder_(str(qrs))
        convQSD = eval(queryParDecoded)
        self._connect_to_redis()
        #self._chkunread()
        self._getUnreadMesg(idatt=convQSD['att_id'], iduser=convQSD['client_id'])
        self._chkunread(idatt=convQSD['att_id'], iduser=convQSD['client_id'])
        self._listen(att=convQSD['att_id'])



    def open(self, *args):
        """
            tornado open method get :UID argoument from querystring and open the websocket connection
        """
        self.qrs = self.get_argument("UID")
        queryParDecoded = base64decoder_(str(self.qrs))
        convQSD = eval(queryParDecoded)
        self.client_id = convQSD['client_id']

        self.stream.set_nodelay(True)
        clients[self.client_id] = self


    def on_message(self, message):
        """
           TODO: DO EVERYTHING ON WEBSOCKET MESSAGE RECEIVED
           :param message (str, not-parsed JSON): data from client (web browser)
        """

    @gen.coroutine
    def _on_update(self, message):

        try:
            body = json.loads(message.body)

            if self.client_id == body['client_id']:

                self.write_message(message.body)
        except Exception, e:
            logging.debug(e)
            pass

    @tornado.gen.engine
    def _listen(self, att):

        yield tornado.gen.Task(self._redis_client.subscribe, att)

        self._redis_client.listen(self._on_update)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def _getUnreadMesg(self,idatt ,iduser): #ritorna il contenuto delle notifiche da gestire
        """
        method for handling messages when the subscriber if offline
        :param idatt = channel ; iduser = client_id
        """
        r = yield tornado.gen.Task(self._redis_client.lrange, str(idatt)+':'+str(iduser), 0, -1)

        i = 0
        for name in r:
            bodyNoty = json.loads(name)

            if "ricevuta" in bodyNoty:  # controllo la chiave 'ricevuta' se non esiste vuol dire che e' stata gia letta

                if bodyNoty["ricevuta"] == 0:

                    self.write_message(name)
                    del bodyNoty["ricevuta"]

                    r = redis.StrictRedis(host=REDIS_SERVER, port=REDIS_PORT, db=REDIS_DB)
                    r.lset(str(idatt)+':'+str(iduser), i, json.dumps(bodyNoty))

            else:
                print('non esiste')

            i += 1


    @tornado.web.asynchronous
    @tornado.gen.engine
    def _chkunread(self,idatt,iduser): #ritorna il numero di notifiche da gestire

        yield tornado.gen.Task(self._redis_client.llen, '13:158')   #yield tornado.gen.Task(self._redis_client.subscribe, 'REDIS_UPDATES_CHANNEL')

    def on_close(self):

        if self.client_id in clients:
            del clients[self.client_id]
            self._redis_client.punsubscribe('*')
            self._redis_client.disconnect()

    def check_origin(self, origin):
        """
        Check if incoming connection is in supported domain
        :param origin (str): Origin/Domain of connection
        """
        return True

    def _connect_to_redis(self):

        self._redis_client = tornadoredis.Client(host=REDIS_SERVER, port=REDIS_PORT, selected_db=REDIS_DB)
        self._redis_client.connect()


application = tornado.web.Application([
    (r'/ws-noty', WebSocketHandler), #RICEZIONE
    (r'/msg', NewMessage), #INVIO
])


if __name__ == "__main__":
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(application)
    c = http_server.listen(8888)
    print '*** Websocket Server Started at %s***' + str(c)
    tornado.ioloop.IOLoop.instance().start()

